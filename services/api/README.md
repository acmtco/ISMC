# services/api

FastAPI-сервис: объекты, камеры, зоны, график, отклонения, машина времени.

## Модули

- `main.py` — приложение, `/health`, OpenAPI-метаданные на русском (`/docs` —
  показываем экспертам на питче, docs/05-pitch.md).
- `db.py` / `models_db.py` — SQLite через SQLModel. БД — читающая проекция:
  `objects`/`cameras`/`zones`/`schedule_works` (сидятся из файлов), и
  производные агрегаты `machine_hours`/`deviations` (пересчитываются ночью).
  Сырые `detections.jsonl` в БД не хранятся — остаются файлами.
- `schemas.py` — Pydantic v2 модели ответов, 1:1 с `docs/02-data-contract.md`.
- `repositories.py` — доступ к данным для роутеров (БД + файлы).
- `routers/objects.py` — `/api/objects`, `.../live`, `.../gantt`,
  `.../economics`, `POST .../schedule` (импорт XLSX/MSPDI).
- `routers/deviations.py` — лента отклонений, карточка, `POST .../act` (PDF).
- `routers/cameras.py` — `POST /api/cameras/{id}/zones`.
- `routers/replay.py` — `GET /api/objects/{id}/replay`: "машина времени" —
  предрассчитанный период через Server-Sent Events с ускорением `speed`.
- `scheduler.py` — APScheduler: опрос камер в режиме `live` (по расписанию,
  `config/api.yaml`), ночной пересчёт `machine_hours`/`deviations` из
  накопленных `detections.jsonl`.
- `act.py` — PDF-акт по отклонению (`fpdf2` + `data/ref/fonts/DejaVuSans.ttf`
  для кириллицы).
- `seed.py` — наполняет БД из `data/ref/objects.json`/`schedule.json` при
  старте (идемпотентно).
- `config.py` — пути и конфиги из переменных окружения (`.env.example`).

Хранилище: SQLite (dev), PostgreSQL (профиль prod в `docker-compose.yml`),
подключение через `HG_DB_URL`.

Точка входа: `services.api.main:app` (`uvicorn`).
