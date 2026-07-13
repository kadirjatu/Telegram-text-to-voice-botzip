# Telegram bot service -- deployable standalone on Railway as its own service.
# Self-contained: only needs this folder (bot.py + tts/ engine + requirements.txt).
# This is a background worker (Telegram long-polling) -- it does not listen on
# any port, so no PORT/EXPOSE is needed. In Railway, do not attach a public
# domain/networking to this service.

FROM python:3.11-slim

# ffmpeg is required by the Edge-TTS pipeline (mp3 -> ogg/opus for voice notes).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
