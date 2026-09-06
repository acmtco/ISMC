"""Прогон перцепции по реальным кадрам синтетики без обученного детектора.

Весов YOLO в репозитории нет (см. `services/perception/detect.py`), поэтому
боксы и классы берём из ground truth — как будто детектор идеален. Состояние
(active/idle/parked) при этом предсказывает НАШ обученный классификатор по
признакам, реально посчитанным с рендеренных кадров (оптический поток,
HSV-дисперсия), а не по синтетическим ground-truth-значениям признаков. Это
честно тестирует `state.py` и агрегацию машино-часов независимо от качества
детектора (docs/04-metrics.md, разделы 3-4 опираются именно на этот прогон;
разделы 1-2 — только когда появятся веса, см. `detection_metrics.py` и
`tracking_metrics.py`).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from services.perception.pipeline import IncrementalPipeline, PipelineConfig
from services.perception.source import FolderSource
from services.perception.state import StateClassifier
from services.perception.track import TrackedDetection
from services.perception.zones import Zone


class GroundTruthTracker:
    """Подменяет YOLO+BoT-SORT: отдаёт истинные боксы синтетики за текущий
    кадр как "детекции" — тот же приём, что и в тестах пайплайна."""

    def __init__(self, ground_truth_by_ts: dict[str, list[dict]]) -> None:
        self.ground_truth_by_ts = ground_truth_by_ts

    def track(self, ts, image) -> list[TrackedDetection]:
        del image
        objs = self.ground_truth_by_ts.get(ts.isoformat(), [])
        return [
            TrackedDetection(track_id=o["track_id"], cls=o["cls"], conf=o["conf"], bbox=o["bbox"])
            for o in objs
        ]


@dataclass(frozen=True)
class PipelineRunResult:
    detections: list[dict]
    frame_count: int
    elapsed_sec: float

    @property
    def fps(self) -> float:
        return self.frame_count / self.elapsed_sec if self.elapsed_sec > 0 else 0.0


def load_ground_truth_records(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_realistic_pipeline(
    *,
    frames_dir: Path,
    ground_truth_records: list[dict],
    zones: list[Zone],
    camera_id: str,
    state_classifier: StateClassifier,
    max_gap_seconds: float = 60.0,
    feature_window_sec: float = 90.0,
) -> PipelineRunResult:
    """`max_gap_seconds` и `feature_window_sec` должны покрывать реальный
    интервал съёмки — иначе `TrackStitcher` рвёт трек на каждом кадре и
    `FeatureTracker` тут же вымывает предыдущую точку из окна, так что
    `centroid_mad`/`area_mad` всегда 0 независимо от истинного движения."""
    records_by_ts = {r["ts"]: r["objects"] for r in ground_truth_records}
    tracker = GroundTruthTracker(records_by_ts)
    config = PipelineConfig(
        camera_id=camera_id,
        zones=zones,
        max_gap_seconds=max_gap_seconds,
        feature_window_sec=feature_window_sec,
    )
    pipeline = IncrementalPipeline(config, tracker, state_classifier)
    source = FolderSource(frames_dir)

    detections: list[dict] = []
    frame_count = 0
    start = time.perf_counter()
    for frame in source.iter_frames():
        detections.append(pipeline.process_frame(frame))
        frame_count += 1
    elapsed = time.perf_counter() - start

    return PipelineRunResult(detections=detections, frame_count=frame_count, elapsed_sec=elapsed)
