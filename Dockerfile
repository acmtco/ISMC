# Один образ на всё приложение: интерфейс и API отвечают с одного адреса.
# Так проще всего развернуть на любом хостинге и не настраивать CORS —
# браузер обращается к тому же origin, откуда загрузил страницу.

# ── сборка интерфейса ────────────────────────────────────────────────
FROM node:20-slim AS web

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
# Адрес API пустой: запросы идут относительно текущего домена.
ENV VITE_API_URL=""
RUN npm run build


# ── рабочий образ ────────────────────────────────────────────────────
FROM python:3.11-slim

# libGL и libglib нужны opencv-python-headless для загрузки бинарных модулей.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY services ./services
COPY scripts ./scripts
RUN pip install --no-cache-dir .

COPY config ./config
COPY data ./data
COPY --from=web /web/dist ./web/dist

# Пути абсолютные: рабочий каталог процесса может отличаться от /app.
ENV HG_DATA_DIR=/app/data \
    HG_CONFIG_DIR=/app/config \
    HG_DB_URL=sqlite:////app/data/hronograf.db \
    HG_WEB_DIST=/app/web/dist \
    HG_MODE=replay \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Порт задаётся окружением: хостинги назначают его сами.
CMD ["sh", "-c", "uvicorn services.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
