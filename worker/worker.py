import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import redis
import requests
from minio import Minio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
QUEUE_KEY = "toWorkers"

INPUT_BUCKET = "queue"
OUTPUT_BUCKET = "output"

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
)

storage = Minio(
    os.getenv("S3_ENDPOINT", "localhost:9000"),
    access_key=os.getenv("S3_ACCESS_KEY", "rustfsadmin"),
    secret_key=os.getenv("S3_SECRET_KEY", "rustfsadmin"),
    secure=os.getenv("S3_SECURE", "false").lower() == "true",
)

TRACKS = ["bass", "drums", "vocals", "other"]


def log_message(message):
    logger.info(message)
    try:
        redis_client.lpush("logging", message)
    except redis.RedisError:
        logger.warning("Unable to write to Redis logging queue")


def process_song(job):
    songhash = job["songhash"]
    model = job.get("model", "mdx_extra")
    callback = job.get("callback")

    log_message(f"Starting separation: {songhash}")

    with tempfile.TemporaryDirectory() as temp_dir:
        workdir = Path(temp_dir)
        input_file = workdir / f"{songhash}.mp3"
        output_dir = workdir / "output"

        # Download the source MP3 from RustFS.
        storage.fget_object(
            INPUT_BUCKET,
            f"{songhash}.mp3",
            str(input_file),
        )

        log_message(f"Downloaded input MP3: {songhash}")

        # Run DEMUCS as a separate process.
        command = [
            "python",
            "-m",
            "demucs.separate",
            "--mp3",
            "-n",
            model,
            "--out",
            str(output_dir),
            str(input_file),
        ]

        logger.info("Running DEMUCS for %s", songhash)

        subprocess.run(
            command,
            check=True,
            timeout=1800,
        )

        # Upload all four separated tracks.
        for track in TRACKS:
            track_file = (
                output_dir
                / model
                / songhash
                / f"{track}.mp3"
            )

            if not track_file.is_file():
                raise FileNotFoundError(
                    f"Missing DEMUCS output: {track_file}"
                )

            storage.fput_object(
                OUTPUT_BUCKET,
                f"{songhash}-{track}.mp3",
                str(track_file),
                content_type="audio/mpeg",
            )

            log_message(
                f"Uploaded {track}.mp3 for {songhash}"
            )

    # Optional callback after successful processing.
    if callback:
        try:
            if isinstance(callback, dict):
                url = callback.get("url")
                payload = callback.get(
                    "payload", {"hash": songhash}
                )
            elif isinstance(callback, str):
                url = callback
                payload = {"hash": songhash}
            else:
                url = None

            if url:
                if not url.startswith(("http://", "https://")):
                    raise ValueError("Unsupported callback URL")

                requests.post(
                    url,
                    json=payload,
                    timeout=10,
                )
        except Exception as exc:
            logger.warning("Callback failed: %s", exc)

    log_message(f"Completed separation: {songhash}")


def main():
    logger.info("DEMUCS worker starting")

    while True:
        try:
            # Wait until Redis has a new job.
            result = redis_client.brpop(
                QUEUE_KEY,
                timeout=5,
            )

            if result is None:
                continue

            _, message = result
            job = json.loads(message)

            process_song(job)

        except Exception:
            logger.exception("Worker processing error")
            time.sleep(5)


if __name__ == "__main__":
    main()
