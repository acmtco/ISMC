from pathlib import Path

import pytest

from scripts.eval.pipeline_run import load_ground_truth_records, run_realistic_pipeline
from scripts.make_synthetic import generate
from scripts.synth.scenario import load_scenario
from services.perception.state import StateClassifier, train
from services.perception.zones import Zone as PerceptionZone


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    scenario = load_scenario(Path("data/ref/scenario_demo.yaml"))
    tmp_path = tmp_path_factory.mktemp("eval_pipeline")
    generate(
        scenario,
        days=5,
        sprites_dir=tmp_path / "sprites",
        out_dir=tmp_path / "frames",
        benchmark_dir=tmp_path / "bench",
    )
    model_path = tmp_path / "state.joblib"
    train(tmp_path / "bench" / "ground_truth.jsonl", model_path)
    classifier = StateClassifier.load(model_path)
    return scenario, tmp_path, classifier


def test_run_realistic_pipeline_produces_one_record_per_frame(dataset):
    scenario, tmp_path, classifier = dataset
    ground_truth = load_ground_truth_records(tmp_path / "bench" / "ground_truth.jsonl")
    zones = [PerceptionZone(zone_id=z.zone_id, polygon=z.polygon) for z in scenario.zones]
    interval = scenario.capture_interval_min * 60

    result = run_realistic_pipeline(
        frames_dir=tmp_path / "frames" / scenario.camera_id,
        ground_truth_records=ground_truth,
        zones=zones,
        camera_id=scenario.camera_id,
        state_classifier=classifier,
        max_gap_seconds=interval * 1.5,
        feature_window_sec=interval * 3,
    )

    assert result.frame_count == len(ground_truth)
    assert len(result.detections) == len(ground_truth)
    assert result.elapsed_sec > 0
    assert result.fps > 0
    for record in result.detections:
        assert set(record) == {"camera_id", "ts", "frame_uri", "quality", "objects"}


def test_run_realistic_pipeline_preserves_object_count_per_frame(dataset):
    scenario, tmp_path, classifier = dataset
    ground_truth = load_ground_truth_records(tmp_path / "bench" / "ground_truth.jsonl")
    zones = [PerceptionZone(zone_id=z.zone_id, polygon=z.polygon) for z in scenario.zones]
    interval = scenario.capture_interval_min * 60

    result = run_realistic_pipeline(
        frames_dir=tmp_path / "frames" / scenario.camera_id,
        ground_truth_records=ground_truth,
        zones=zones,
        camera_id=scenario.camera_id,
        state_classifier=classifier,
        max_gap_seconds=interval * 1.5,
        feature_window_sec=interval * 3,
    )

    for gt_record, pred_record in zip(ground_truth, result.detections, strict=True):
        assert len(pred_record["objects"]) == len(gt_record["objects"])
        for gt_obj, pred_obj in zip(gt_record["objects"], pred_record["objects"], strict=True):
            assert pred_obj["cls"] == gt_obj["cls"]
            assert pred_obj["state"] in {"active", "idle", "parked"}


def test_track_continuity_gives_nonzero_centroid_mad_for_moving_units(dataset):
    """Регрессия: `max_gap_seconds`/`feature_window_sec` слишком маленькие
    (дефолт рассчитан на плотное видео) рвут непрерывность трека на каждом
    кадре при разреженной съёмке — тогда centroid_mad/area_mad всегда 0
    независимо от истинного движения (см. докстринг pipeline_run.py)."""
    scenario, tmp_path, classifier = dataset
    ground_truth = load_ground_truth_records(tmp_path / "bench" / "ground_truth.jsonl")
    zones = [PerceptionZone(zone_id=z.zone_id, polygon=z.polygon) for z in scenario.zones]
    interval = scenario.capture_interval_min * 60

    result = run_realistic_pipeline(
        frames_dir=tmp_path / "frames" / scenario.camera_id,
        ground_truth_records=ground_truth,
        zones=zones,
        camera_id=scenario.camera_id,
        state_classifier=classifier,
        max_gap_seconds=interval * 1.5,
        feature_window_sec=interval * 3,
    )
    centroid_mads = [
        o["features"]["centroid_mad"] for r in result.detections for o in r["objects"]
    ]
    assert any(v > 0 for v in centroid_mads)


def test_default_gap_settings_would_zero_out_centroid_mad(dataset):
    """То же самое явно демонстрирует регрессию при дефолтных (не подходящих
    для разреженной съёмки) настройках — фиксирует причину бага."""
    scenario, tmp_path, classifier = dataset
    ground_truth = load_ground_truth_records(tmp_path / "bench" / "ground_truth.jsonl")
    zones = [PerceptionZone(zone_id=z.zone_id, polygon=z.polygon) for z in scenario.zones]

    result = run_realistic_pipeline(
        frames_dir=tmp_path / "frames" / scenario.camera_id,
        ground_truth_records=ground_truth,
        zones=zones,
        camera_id=scenario.camera_id,
        state_classifier=classifier,
        # дефолты (60с/90с) — намного меньше интервала съёмки (20 мин)
    )
    centroid_mads = [
        o["features"]["centroid_mad"] for r in result.detections for o in r["objects"]
    ]
    assert all(v == 0.0 for v in centroid_mads)
