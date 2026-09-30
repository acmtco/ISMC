"""Сквозной прогон: кадр -> детекции -> треки -> зона -> состояние.

Пишет `detections.jsonl` по контракту `docs/02-data-contract.md`, раздел 3.
Плохое качество кадра (`quality.score < 0.5`) не исключается здесь — это
честно записывается в `quality`, а решение не формировать на этих данных
отклонение принимает аналитика (docs/01-principles.md, правило 4).

`IncrementalPipeline` держит состояние (трекер, окна признаков, предыдущий
кадр) между вызовами `process_frame()` — это позволяет `run_pipeline()`
(пакетный прогон по всему источнику) и планировщику `services/api/scheduler.py`
(опрос камеры по расписанию, кадр за кадром) использовать один и тот же код,
не дублируя логику.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from services.perception.quality import assess_quality
from services.perception.source import Frame, FrameSource
from services.perception.state import (
    FeatureTracker,
    StateClassifier,
    crop,
    hsv_variance,
    optical_flow_magnitude,
)
from services.perception.track import TrackedDetection, TrackStitcher
from services.perception.zones import Zone, assign_zone


class RawTracker(Protocol):
    """Поставляет детекции с "сырыми" (ещё не склеенными) track_id на кадр."""

    def track(self, ts: datetime, image: np.ndarray) -> list[TrackedDetection]: ...


@dataclass(frozen=True)
class PipelineConfig:
    camera_id: str
    zones: list[Zone]
    feature_window_sec: float = 90.0
    max_gap_seconds: float = 60.0
    max_centroid_distance_px: float = 80.0


def _zone_lookup(config: PipelineConfig) -> Callable[[list[float]], str | None]:
    def _lookup(bbox: list[float]) -> str | None:
        return assign_zone(bbox, config.zones)

    return _lookup


class IncrementalPipeline:
    """Обрабатывает кадры по одному, храня состояние между вызовами —
    трекер, окна признаков движения, предыдущий кадр (для оптического
    потока). Один экземпляр на камеру."""

    def __init__(
        self, config: PipelineConfig, tracker: RawTracker, state_classifier: StateClassifier
    ) -> None:
        self.config = config
        self.tracker = tracker
        self.state_classifier = state_classifier
        self.stitcher = TrackStitcher(config.max_gap_seconds, config.max_centroid_distance_px)
        self.feature_tracker = FeatureTracker(config.feature_window_sec)
        self.zone_of = _zone_lookup(config)
        self.prev_gray: np.ndarray | None = None

    def process_frame(self, frame: Frame) -> dict[str, Any]:
        quality = assess_quality(frame.image)
        raw_detections = self.tracker.track(frame.ts, frame.image)
        stitched = self.stitcher.update(frame.ts, raw_detections, self.zone_of)
        gray = cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY)

        objects = [
            _build_object(
                det,
                frame.ts,
                frame.image,
                gray,
                self.prev_gray,
                self.feature_tracker,
                self.zone_of,
                self.state_classifier,
            )
            for det in stitched
        ]
        self.prev_gray = gray

        return {
            "camera_id": self.config.camera_id,
            "ts": frame.ts.isoformat(),
            "frame_uri": frame.uri or "",
            "quality": quality.as_dict(),
            "objects": objects,
        }


def run_pipeline(
    source: FrameSource,
    tracker: RawTracker,
    state_classifier: StateClassifier,
    config: PipelineConfig,
    out_path: Path,
) -> int:
    """Пакетный прогон по всему источнику. Возвращает число обработанных кадров."""
    pipeline = IncrementalPipeline(config, tracker, state_classifier)
    frame_count = 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for frame in source.iter_frames():
            record = pipeline.process_frame(frame)
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")
            frame_count += 1

    return frame_count


def _build_object(
    det: TrackedDetection,
    ts: datetime,
    image: np.ndarray,
    gray: np.ndarray,
    prev_gray: np.ndarray | None,
    feature_tracker: FeatureTracker,
    zone_of: Callable[[list[float]], str | None],
    state_classifier: StateClassifier,
) -> dict[str, Any]:
    movement = feature_tracker.update(det.track_id, ts, det.bbox)

    flow_mag = 0.0
    if prev_gray is not None:
        flow_mag = optical_flow_magnitude(crop(prev_gray, det.bbox), crop(gray, det.bbox))

    features = {
        "centroid_mad": movement["centroid_mad"],
        "area_mad": movement["area_mad"],
        "flow_mag": round(flow_mag, 2),
        "hsv_var": round(hsv_variance(crop(image, det.bbox)), 2),
    }
    state, state_conf = state_classifier.predict(features, movement["seconds_since_movement"])

    return {
        "track_id": det.track_id,
        "cls": det.cls,
        "conf": round(det.conf, 3),
        "bbox": [round(v, 1) for v in det.bbox],
        "zone_id": zone_of(det.bbox),
        "state": state,
        "state_conf": round(state_conf, 2),
        "features": features,
    }
