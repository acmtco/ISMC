"""Сквозная оценка на `data/benchmark/` — единственный источник чисел для
`docs/04-metrics.md` (числа руками не пишем, см. докстринг самого файла).

Раздел 1 (детекция) и раздел 2 (трекинг) требуют обученных весов YOLO
(`models/`, см. `services/perception/detect.py`) — их в репозитории нет, эти
разделы честно помечаются "нет данных" (CLAUDE.md, правило 4), а не
подделываются. Разделы 3-5 (состояние, машино-часы, отклонения) считаются
по-настоящему: боксы/классы берутся из ground truth (как будто детектор
идеален), а состояние предсказывает наш обученный классификатор по
признакам, реально посчитанным с рендеренных кадров синтетики — см.
`scripts/eval/pipeline_run.py`.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.eval.detection_metrics import run_detector_evaluation
from scripts.eval.deviations_metrics import evaluate_deviations
from scripts.eval.machine_hours_metrics import evaluate_machine_hours
from scripts.eval.performance import estimate_performance
from scripts.eval.pipeline_run import run_realistic_pipeline
from scripts.eval.report import render_markdown, save_charts
from scripts.eval.state_metrics import evaluate_state_classifier
from scripts.eval.tracking_metrics import run_tracking_evaluation
from scripts.make_synthetic import generate as generate_synthetic
from scripts.synth.classes import CLASSES
from scripts.synth.scenario import load_scenario
from services.analytics.deviations import DeviationEngine
from services.analytics.machine_hours import aggregate_machine_hours
from services.perception.state import StateClassifier
from services.perception.state import train as train_state_classifier
from services.perception.zones import Zone as PerceptionZone

MSK = timezone(timedelta(hours=3))


def _ensure_benchmark(
    scenario_path: Path, benchmark_dir: Path, sprites_dir: Path, out_dir: Path, days: int | None
) -> None:
    ground_truth_path = benchmark_dir / "ground_truth.jsonl"
    if ground_truth_path.exists():
        return
    print(
        f"{ground_truth_path} не найден — генерирую синтетический бенчмарк "
        "(scripts/make_synthetic.py)…"
    )
    scenario = load_scenario(scenario_path)
    generate_synthetic(scenario, days or scenario.days, sprites_dir, out_dir, benchmark_dir)


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _benchmark_day_count(ground_truth_records: list[dict]) -> int:
    return len({datetime.fromisoformat(r["ts"]).date() for r in ground_truth_records})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--scenario", type=Path, default=Path("data/ref/scenario_demo.yaml"))
    parser.add_argument("--benchmark-dir", type=Path, default=Path("data/benchmark"))
    parser.add_argument("--frames-dir", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--sprites-dir", type=Path, default=Path("data/ref/sprites"))
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="переопределить число суток при автогенерации бенчмарка (по умолчанию — из сценария)",
    )
    parser.add_argument("--object-id", default="OBJ-001")
    parser.add_argument("--perception-config", type=Path, default=Path("config/perception.yaml"))
    parser.add_argument(
        "--work-signatures", type=Path, default=Path("data/ref/work_signatures.json")
    )
    parser.add_argument("--matching-config", type=Path, default=Path("config/matching.yaml"))
    parser.add_argument("--thresholds", type=Path, default=Path("config/thresholds.yaml"))
    parser.add_argument(
        "--machine-hour-cost", type=Path, default=Path("data/ref/machine_hour_cost.json")
    )
    parser.add_argument("--out", type=Path, default=Path("docs/04-metrics.md"))
    parser.add_argument("--img-dir", type=Path, default=Path("docs/img"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    _ensure_benchmark(
        args.scenario, args.benchmark_dir, args.sprites_dir, args.frames_dir, args.days
    )
    scenario = load_scenario(args.scenario)

    ground_truth_path = args.benchmark_dir / "ground_truth.jsonl"
    ground_truth_records = _read_jsonl(ground_truth_path)
    expected_deviations = _read_jsonl(args.benchmark_dir / "expected_deviations.jsonl")
    benchmark_days = _benchmark_day_count(ground_truth_records)

    # --- Раздел 3: обучаем классификатор состояния прямо в рамках прогона,
    # чтобы метрики всегда отражали текущий код и данные.
    print("Обучаю классификатор состояния…")
    with tempfile.TemporaryDirectory() as tmp:
        model_path = Path(tmp) / "state.joblib"
        train_state_classifier(ground_truth_path, model_path)
        state_classifier = StateClassifier.load(model_path)
    state_eval = evaluate_state_classifier(ground_truth_path)
    print(f"  accuracy={state_eval.accuracy:.3f}")

    # --- Разделы 3-5: реалистичный прогон перцепции (боксы/классы — ground
    # truth, состояние — наш классификатор по реальным признакам с кадров).
    print("Прогоняю перцепцию по кадрам синтетики (без обученного детектора)…")
    zones = [PerceptionZone(zone_id=z.zone_id, polygon=z.polygon) for z in scenario.zones]
    frames_dir = args.frames_dir / scenario.camera_id
    # Синтетика снимает раз в scenario.capture_interval_min минут — на порядки
    # реже, чем предполагают дефолты PipelineConfig (рассчитаны на плотное
    # видео). Разрыв трека и окно признаков должны покрывать этот интервал,
    # иначе MAD-признаки движения всегда будут нулевыми (см. pipeline_run.py).
    capture_interval_sec = scenario.capture_interval_min * 60
    pipeline_result = run_realistic_pipeline(
        frames_dir=frames_dir,
        ground_truth_records=ground_truth_records,
        zones=zones,
        camera_id=scenario.camera_id,
        state_classifier=state_classifier,
        max_gap_seconds=capture_interval_sec * 1.5,
        feature_window_sec=capture_interval_sec * 3,
    )
    print(
        f"  {pipeline_result.frame_count} кадров за {pipeline_result.elapsed_sec:.1f}с "
        f"({pipeline_result.fps:.1f} fps)"
    )

    # --- Раздел 4: машино-часы, пайплайн vs ground truth.
    mh_error = evaluate_machine_hours(
        pipeline_result.detections, ground_truth_records, object_id=args.object_id
    )
    predicted_rows = aggregate_machine_hours(pipeline_result.detections, object_id=args.object_id)
    truth_rows = aggregate_machine_hours(ground_truth_records, object_id=args.object_id)
    print(f"  MAE mh_active={mh_error.mae_active_hours:.2f}ч, MAPE={mh_error.mape_active_pct:.1f}%")

    # --- Раздел 5: отклонения.
    engine = DeviationEngine.load(
        work_signatures_path=args.work_signatures,
        matching_config_path=args.matching_config,
        thresholds_path=args.thresholds,
        machine_hour_cost_path=args.machine_hour_cost,
    )
    last_day = max(datetime.fromisoformat(r["ts"]).date() for r in ground_truth_records)
    as_of = datetime.combine(last_day, datetime.min.time(), tzinfo=MSK) + timedelta(days=1)
    deviation_eval = evaluate_deviations(
        scenario=scenario,
        machine_hours=predicted_rows,
        detections=pipeline_result.detections,
        expected_deviations=expected_deviations,
        engine=engine,
        as_of=as_of,
    )
    print(
        f"  отклонения: precision={deviation_eval.overall.precision}, "
        f"recall={deviation_eval.overall.recall}"
    )

    # --- Разделы 1-2: только если есть обученные веса детектора.
    print("Проверяю веса детектора для разделов 1-2…")
    detection = run_detector_evaluation(
        detector_config_path=args.perception_config,
        ground_truth_path=ground_truth_path,
        classes=CLASSES,
    )
    tracking = run_tracking_evaluation(
        detector_config_path=args.perception_config, ground_truth_path=ground_truth_path
    )
    if detection is None:
        print("  весов нет — разделы 1-2 отчёта будут пустыми")

    # --- Раздел 7: производительность (без инференса детектора).
    frames_per_camera_day = pipeline_result.frame_count / benchmark_days if benchmark_days else 0.0
    performance = estimate_performance(pipeline_result.fps, frames_per_camera_day)

    # --- Отчёт.
    chart_paths = save_charts(
        args.img_dir,
        state_eval=state_eval,
        predicted_rows=predicted_rows,
        truth_rows=truth_rows,
        deviation_eval=deviation_eval,
    )
    markdown = render_markdown(
        detection=detection,
        tracking=tracking,
        state_eval=state_eval,
        mh_error=mh_error,
        deviation_eval=deviation_eval,
        performance=performance,
        benchmark_days=benchmark_days,
        chart_paths=chart_paths,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    print(f"Отчёт записан: {args.out}")


if __name__ == "__main__":
    main()
