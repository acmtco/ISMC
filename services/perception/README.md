# services/perception

Слой восприятия: кадр → детекции → треки → состояние (`active` / `idle` / `parked` / `unknown`).

Вход: кадры из `data/replay/<camera_id>/` (режим `replay`) или RTSP/HLS-поток (режим `live`),
управляется переменной окружения `HG_MODE`.

Выход: `detections.jsonl`, формат — `docs/02-data-contract.md`, раздел 3.

Стек: YOLO11 (`ultralytics`) + BoT-SORT для трекинга, признаки микродвижения
(`centroid_mad`, `area_mad`, `flow_mag`) для классификации состояния.

Статус: каркас, бизнес-логика не реализована.
