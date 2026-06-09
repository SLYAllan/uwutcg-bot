# Image officielle Playwright (Python + navigateurs + dépendances système préinstallés).
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Paris

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium

COPY . .

# Données persistantes (DB SQLite) montées en volume.
VOLUME ["/app/data"]

CMD ["python", "-m", "bot.main"]
