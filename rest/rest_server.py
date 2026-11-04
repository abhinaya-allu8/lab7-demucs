import base64
import binascii
import hashlib
import io
import json
import os
import re
import uuid

from flask import Flask, jsonify, request, send_file
from minio import Minio
from minio.error import S3Error
from redis import Redis

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

QUEUE_KEY = "toWorkers"
INPUT_BUCKET = "queue"
OUTPUT_BUCKET = "output"

redis_client = Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
    socket_connect_timeout=5,
)

storage = Minio(
    os.getenv("S3_ENDPOINT", "localhost:9000"),
    access_key=os.getenv("S3_ACCESS_KEY", "rustfsadmin"),
    secret_key=os.getenv("S3_SECRET_KEY", "rustfsadmin"),
    secure=os.getenv("S3_SECURE", "false").lower() == "true",
)

TRACKS = {
    "bass.mp3": "bass.mp3",
    "base.mp3": "bass.mp3",
    "vocals.mp3": "vocals.mp3",
    "drums.mp3": "drums.mp3",
    "other.mp3": "other.mp3",
}

HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def valid_hash(songhash):
    return bool(HASH_PATTERN.fullmatch(songhash))


def ensure_buckets():
    for bucket in (INPUT_BUCKET, OUTPUT_BUCKET):
        if not storage.bucket_exists(bucket):
            storage.make_bucket(bucket)


@app.get("/")
def home():
    return jsonify(
        service="Music Separation Server",
        status="running",
    )


@app.post("/apiv1/separate")
def separate():
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not isinstance(data.get("mp3"), str):
        return jsonify(error="Expected JSON with base64 mp3 field"), 400

    try:
        mp3_bytes = base64.b64decode(data["mp3"], validate=True)
    except (ValueError, binascii.Error):
        return jsonify(error="Invalid base64 MP3"), 400

    if not mp3_bytes:
        return jsonify(error="Empty MP3"), 400

    songhash = hashlib.sha256(
        mp3_bytes + uuid.uuid4().bytes
    ).hexdigest()

    model = data.get("model") or "mdx_extra"
    callback = data.get("callback")

    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", model):
        return jsonify(error="Invalid model"), 400

    if callback is not None and not isinstance(callback, (dict, str)):
        return jsonify(error="Invalid callback"), 400

    try:
        ensure_buckets()

        storage.put_object(
            INPUT_BUCKET,
            f"{songhash}.mp3",
            io.BytesIO(mp3_bytes),
            length=len(mp3_bytes),
            content_type="audio/mpeg",
        )

        job = {
            "songhash": songhash,
            "model": model,
            "callback": callback,
        }

        redis_client.lpush(QUEUE_KEY, json.dumps(job))

        return jsonify(
            hash=songhash,
            reason="Song enqueued for separation",
        ), 202

    except Exception:
        app.logger.exception("Failed to enqueue song")
        return jsonify(error="Unable to enqueue song"), 503


@app.get("/apiv1/queue/")
@app.get("/apiv1/queue")
def queue():
    try:
        entries = redis_client.lrange(QUEUE_KEY, 0, -1)
        hashes = []

        for entry in entries:
            try:
                job = json.loads(entry)
                hashes.append(job.get("songhash", entry))
            except (ValueError, TypeError):
                hashes.append(entry)

        return jsonify(queue=hashes)
    except Exception:
        app.logger.exception("Queue lookup failed")
        return jsonify(error="Redis unavailable"), 503


@app.get("/apiv1/track/<songhash>/<track>")
def get_track(songhash, track):
    if not valid_hash(songhash) or track not in TRACKS:
        return jsonify(error="Invalid song hash or track"), 400

    object_name = f"{songhash}-{TRACKS[track]}"

    try:
        obj = storage.get_object(OUTPUT_BUCKET, object_name)
        try:
            audio = obj.read()
        finally:
            obj.close()
            obj.release_conn()

        return send_file(
            io.BytesIO(audio),
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name=track,
        )

    except S3Error as exc:
        if exc.code in ("NoSuchKey", "NoSuchBucket"):
            return jsonify(error="Track not found or not ready"), 404
        app.logger.exception("Storage error")
        return jsonify(error="Storage unavailable"), 503


@app.route(
    "/apiv1/remove/<songhash>/<track>",
    methods=["GET", "DELETE"],
)
def remove_track(songhash, track):
    if not valid_hash(songhash) or track not in TRACKS:
        return jsonify(error="Invalid song hash or track"), 400

    try:
        storage.remove_object(
            OUTPUT_BUCKET,
            f"{songhash}-{TRACKS[track]}",
        )
        return jsonify(
            hash=songhash,
            removed=track,
        )
    except S3Error:
        app.logger.exception("Track removal failed")
        return jsonify(error="Unable to remove track"), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
