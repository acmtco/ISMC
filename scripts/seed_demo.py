"""Наполнение демонстрационного стенда настоящим расчётом по бенчмарку.

Зачем отдельный скрипт: чистая установка поднимает пустую базу (объект,
камеры и зоны есть, детекций нет), и все экраны честно показывают «данных
нет». Чтобы жюри увидело работающий прототип, нужно один раз прогнать
конвейер по кадрам бенчмарка и разложить результат по таблицам.

Это НЕ подстановка готовых чисел: машино-часы и отклонения считаются тем же
кодом, что и в продуктивном режиме (`services/analytics`), на кадрах,
сгенерированных `scripts/make_synthetic.py`. Синтетическими здесь являются
входные снимки, а не результат.

Боксы и классы берутся из `ground_truth.jsonl` бенчмарка (как в
`scripts/eval_end2end.py`): так демо не зависит от того, обучен ли уже
детектор на все классы, а состояние техники при этом определяется моделью
по реальным пикселям кадра.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session

from scripts.eval.deviations_metrics import build_schedule_dicts
from scripts.eval.pipeline_run import load_ground_truth_records, run_realistic_pipeline
from scripts.synth.scenario import load_scenario
from services.api import config
from services.api.db import get_engine, init_db
from services.api.scheduler import recompute_object
from services.api.seed import seed_all
from services.perception.state import StateClassifier
from services.perception.zones import load_zones

# Интервал съёмки бенчмарка (`data/ref/scenario_demo.yaml`: capture_interval_min).
# Окна трекинга и признаков должны его покрывать — иначе трек рвётся на
# каждом кадре и признаки движения вырождаются в нули (см. докстринг
# `run_realistic_pipeline`).
CAPTURE_INTERVAL_SEC = 1200.0
GAP_FACTOR = 1.5
FEATURE_WINDOW_FACTOR = 3.0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object-id", default="OBJ-001")
    parser.add_argument("--camera-id", default="CAM-01")
    parser.add_argument("--frames-dir", type=Path, default=Path("data/synthetic/CAM-01"))
    parser.add_argument(
        "--ground-truth", type=Path, default=Path("data/benchmark/ground_truth.jsonl")
    )
    parser.add_argument("--scenario", type=Path, default=Path("data/ref/scenario_demo.yaml"))
    return parser.parse_args(argv)


def write_schedule_json(scenario_path: Path, out_path: Path) -> int:
    """Календарный график демо выводится из того же сценария, по которому
    сгенерированы кадры, — иначе план и факт описывали бы разные стройки.
    Плановые машино-часы считаются как в оценке (`build_schedule_dicts`):
    состав техники × доля активного времени × часы смены × число суток."""
    scenario = load_scenario(scenario_path)
    entries = build_schedule_dicts(scenario)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(entries)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    if not args.frames_dir.exists():
        raise SystemExit(
            f"нет кадров: {args.frames_dir}. Сначала выполните "
            "`python -m scripts.make_synthetic --days 30`"
        )

    state_path = config.models_dir() / "state.joblib"
    if not state_path.exists():
        raise SystemExit(
            f"нет модели состояния: {state_path}. Обучите её: "
            "`python -m services.perception.state "
            "--ground-truth data/benchmark/ground_truth.jsonl`"
        )

    schedule_path = config.ref_dir() / "schedule.json"
    n_works = write_schedule_json(args.scenario, schedule_path)
    print(f"график записан: {schedule_path} ({n_works} работ)")

    init_db()
    with Session(get_engine()) as session:
        seed_all(
            session,
            objects_json_path=config.objects_json_path(),
            schedule_json_path=schedule_path,
        )

    zones = load_zones(config.objects_json_path(), args.camera_id)
    result = run_realistic_pipeline(
        frames_dir=args.frames_dir,
        ground_truth_records=load_ground_truth_records(args.ground_truth),
        zones=zones,
        camera_id=args.camera_id,
        state_classifier=StateClassifier.load(state_path),
        max_gap_seconds=CAPTURE_INTERVAL_SEC * GAP_FACTOR,
        feature_window_sec=CAPTURE_INTERVAL_SEC * FEATURE_WINDOW_FACTOR,
    )
    print(f"обработано кадров: {result.frame_count} ({result.fps:.1f} кадр/с)")

    out_path = config.detections_path(args.camera_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for record in result.detections:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")
    print(f"детекции записаны: {out_path}")

    with Session(get_engine()) as session:
        n = recompute_object(session, args.object_id, [args.camera_id])
    print(f"пересчёт выполнен, сформировано отклонений: {n}")
    print(f"время расчёта: {datetime.now(UTC).isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
