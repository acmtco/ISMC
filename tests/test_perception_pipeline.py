import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.make_synthetic import generate
from scripts.synth.scenario import load_scenario
from services.perception.pipeline import PipelineConfig, run_pipeline
from services.perception.source import FolderSource
from services.perception.state import StateClassifier, train
from services.perception.track import TrackedDetection
from services.perception.zones import Zone as PerceptionZone


class _GroundTruthTracker:
    """Подменяет YOLO+BoT-SORT: отдаёт истинные боксы синтетики как "детекции"
    текущего кадра — так тест проверяет склейку/зоны/состояние/запись без
    реальной модели (docs/01-principles.md, правило 2: без сети и GPU)."""

    def __init__(self, records_by_ts: dict[str, list[dict]]) -> None:
        self.records_by_ts = records_by_ts

    def track(self, ts: datetime, image) -> list[TrackedDetection]:
        del image
        objs = self.records_by_ts.get(ts.isoformat(), [])
        return [
            TrackedDetection(track_id=o["track_id"], cls=o["cls"], conf=o["conf"], bbox=o["bbox"])
            for o in objs
        ]


@pytest.fixture(scope="module")
def synthetic_dataset(tmp_path_factory):
    base_scenario = load_scenario(Path("data/ref/scenario_demo.yaml"))
    # окно, где активны оба вида работ (W-014 и W-101) — богаче для проверки
    scenario = replace(base_scenario, start_date=date(2026, 9, 16))

    tmp_path = tmp_path_factory.mktemp("pipeline_ds")
    frame_count = generate(
        scenario,
        days=2,
        sprites_dir=tmp_path / "sprites",
        out_dir=tmp_path / "frames",
        benchmark_dir=tmp_path / "bench",
    )
    assert frame_count > 0
    return scenario, tmp_path


def _load_ground_truth(bench_dir: Path) -> list[dict]:
    lines = (bench_dir / "ground_truth.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_pipeline_writes_valid_schema_and_matches_zone_assignment(synthetic_dataset, tmp_path):
    scenario, dataset_dir = synthetic_dataset
    gt_records = _load_ground_truth(dataset_dir / "bench")
    assert any(r["objects"] for r in gt_records), "фикстура должна содержать хотя бы одну технику"

    records_by_ts = {r["ts"]: r["objects"] for r in gt_records}
    zones = [PerceptionZone(zone_id=z.zone_id, polygon=z.polygon) for z in scenario.zones]

    model_path = tmp_path / "state.joblib"
    train(dataset_dir / "bench" / "ground_truth.jsonl", model_path, seed=42)
    classifier = StateClassifier.load(model_path)

    out_path = tmp_path / "detections.jsonl"
    source = FolderSource(dataset_dir / "frames" / scenario.camera_id)
    config = PipelineConfig(camera_id=scenario.camera_id, zones=zones)

    tracker = _GroundTruthTracker(records_by_ts)
    frame_count = run_pipeline(source, tracker, classifier, config, out_path)
    assert frame_count == len(gt_records)

    out_lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(out_lines) == frame_count

    for gt_record, out_line in zip(gt_records, out_lines, strict=True):
        out_record = json.loads(out_line)
        assert set(out_record) == {"camera_id", "ts", "frame_uri", "quality", "objects"}
        assert out_record["camera_id"] == scenario.camera_id
        assert out_record["ts"] == gt_record["ts"]
        assert len(out_record["objects"]) == len(gt_record["objects"])

        for gt_obj, out_obj in zip(gt_record["objects"], out_record["objects"], strict=True):
            assert set(out_obj) == {
                "track_id",
                "cls",
                "conf",
                "bbox",
                "zone_id",
                "state",
                "state_conf",
                "features",
            }
            assert out_obj["cls"] == gt_obj["cls"]
            # зона считается той же логикой (assign_zone по тем же полигонам) —
            # должна совпасть с зоной, которую заложил генератор синтетики
            assert out_obj["zone_id"] == gt_obj["zone_id"]
            assert out_obj["state"] in {"active", "idle", "parked"}
            assert 0.0 <= out_obj["state_conf"] <= 1.0


def test_pipeline_stitches_track_ids_stably_across_frames(synthetic_dataset, tmp_path):
    scenario, dataset_dir = synthetic_dataset
    gt_records = _load_ground_truth(dataset_dir / "bench")
    records_by_ts = {r["ts"]: r["objects"] for r in gt_records}
    zones = [PerceptionZone(zone_id=z.zone_id, polygon=z.polygon) for z in scenario.zones]

    model_path = tmp_path / "state.joblib"
    train(dataset_dir / "bench" / "ground_truth.jsonl", model_path, seed=42)
    classifier = StateClassifier.load(model_path)

    out_path = tmp_path / "detections.jsonl"
    source = FolderSource(dataset_dir / "frames" / scenario.camera_id)
    config = PipelineConfig(camera_id=scenario.camera_id, zones=zones)
    run_pipeline(source, _GroundTruthTracker(records_by_ts), classifier, config, out_path)

    out_records = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]

    # один и тот же исходный track_id (ground truth) должен всегда получать
    # один и тот же стабильный (склеенный) track_id на выходе пайплайна
    gt_to_stitched: dict[int, int] = {}
    for gt_record, out_record in zip(gt_records, out_records, strict=True):
        for gt_obj, out_obj in zip(gt_record["objects"], out_record["objects"], strict=True):
            gt_id = gt_obj["track_id"]
            if gt_id in gt_to_stitched:
                assert out_obj["track_id"] == gt_to_stitched[gt_id]
            else:
                gt_to_stitched[gt_id] = out_obj["track_id"]
