"""MOTA, IDF1, переключения ID (docs/04-metrics.md, раздел 2).

Тот же принцип, что и в `detection_metrics.py`: без обученного детектора
трекать нечего — раздел честно пуст. Сопоставление кадр-за-кадром и сами
метрики — из `motmetrics` (эталонная библиотека MOTChallenge), не
самописные, чтобы не рисковать тонкими ошибками в редко исполняемом коде.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import motmetrics as mm
import numpy as np

from scripts.eval.detection_metrics import iou
from services.perception.detect import Detector, DetectorConfig


@dataclass(frozen=True)
class TrackedBox:
    track_id: int
    bbox: list[float]


@dataclass(frozen=True)
class TrackingMetrics:
    mota: float
    idf1: float
    id_switches: int
    num_frames: int


def compute_tracking_metrics(
    ground_truth_by_frame: list[list[TrackedBox]],
    predicted_by_frame: list[list[TrackedBox]],
    iou_threshold: float = 0.5,
) -> TrackingMetrics:
    acc = mm.MOTAccumulator(auto_id=True)
    for gts, preds in zip(ground_truth_by_frame, predicted_by_frame, strict=True):
        gt_ids = [g.track_id for g in gts]
        pred_ids = [p.track_id for p in preds]
        distances = np.full((len(gts), len(preds)), np.nan)
        for i, g in enumerate(gts):
            for j, p in enumerate(preds):
                v = iou(g.bbox, p.bbox)
                if v >= iou_threshold:
                    distances[i, j] = 1.0 - v
        acc.update(gt_ids, pred_ids, distances)

    mh = mm.metrics.create()
    summary = mh.compute(acc, metrics=["mota", "idf1", "num_switches"], name="eval")
    return TrackingMetrics(
        mota=float(summary["mota"].iloc[0]),
        idf1=float(summary["idf1"].iloc[0]),
        id_switches=int(summary["num_switches"].iloc[0]),
        num_frames=len(ground_truth_by_frame),
    )


def run_tracking_evaluation(
    *,
    detector_config_path: Path,
    ground_truth_path: Path,
) -> TrackingMetrics | None:
    """None, если весов детектора нет."""
    config = DetectorConfig.from_yaml(detector_config_path)
    if not config.weights_path.exists():
        return None

    detector = Detector(config)
    from services.perception.track import YoloTracker

    tracker = YoloTracker(detector)

    from PIL import Image

    gt_by_frame: list[list[TrackedBox]] = []
    pred_by_frame: list[list[TrackedBox]] = []
    with Path(ground_truth_path).open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            image = np.array(Image.open(record["frame_uri"]).convert("RGB"))[:, :, ::-1]
            ts = datetime.fromisoformat(record["ts"])
            raw = tracker.track(ts, image)
            pred_by_frame.append([TrackedBox(d.track_id, d.bbox) for d in raw])
            gt_by_frame.append([TrackedBox(o["track_id"], o["bbox"]) for o in record["objects"]])

    return compute_tracking_metrics(gt_by_frame, pred_by_frame)
