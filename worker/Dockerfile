FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir demucs

RUN python -c "import numpy, scipy, soundfile, demucs.separate; print('DEMUCS imports OK')"

RUN python -c "import numpy, scipy, soundfile, demucs.separate; print('DEMUCS imports OK')"

COPY worker.py .

CMD ["python", "worker.py"]
