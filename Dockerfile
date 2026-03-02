FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-fra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY static/ ./static/
COPY start.py .

# Répertoire pour ChromaDB (persistant via volume Railway si configuré)
RUN mkdir -p /data/chroma

ENV PYTHONUNBUFFERED=1
ENV CHROMA_DATA_PATH=/data/chroma

EXPOSE 8000

# start.py lit PORT depuis l'environnement (Railway injecte PORT au runtime)
CMD ["python", "start.py"]
