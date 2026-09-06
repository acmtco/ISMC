"""BoT-SORT трекинг + собственная склейка разрывов track_id.

`model.track(...)` (ultralytics + BoT-SORT) ассоциирует объекты только между
соседними кадрами плотного видео. На разреженной съёмке (кадр раз в десятки
секунд/минут) трек почти всегда обрывается и переоткрывается с новым id.
`TrackStitcher` восстанавливает непрерывность поверх сырых id: если объект
того же класса пропал и появился рядом в той же зоне в течение
`max_gap_seconds`, ему возвращается прежний (стабильный) track_id.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import numpy as np


@dataclass(frozen=True)
class TrackedDetection:
    track_id: int
    cls: str
    conf: float
    bbox: list[float]


class Trackable(Protocol):
    names: dict[int, str]

    def track(self, image: np.ndarray, **kwargs: Any) -> list[Any]: ...


def raw_track(
    model: Trackable, image: np.ndarray, *, tracker: str = "botsort.yaml", **kwargs: Any
) -> list[TrackedDetection]:
    """Один вызов `model.track(..., persist=True)` -> детекции с "сырыми"
    track_id от BoT-SORT (могут обрываться на разреженной съёмке)."""
    results = model.track(image, tracker=tracker, persist=True, verbose=False, **kwargs)
    result = results[0] if results else None
    detections: list[TrackedDetection] = []
    boxes = getattr(result, "boxes", None) or []
    for box in boxes:
        if box.id is None:
            continue  # BoT-SORT не присвоил id (низкая уверенность ассоциации)
        x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
        bbox = [x1, y1, x2 - x1, y2 - y1]
        detections.append(
            TrackedDetection(
                track_id=int(box.id[0]),
                cls=model.names[int(box.cls[0])],
                conf=float(box.conf[0]),
                bbox=bbox,
            )
        )
    return detections


class YoloTracker:
    """Адаптер `Detector` (модель ultralytics) -> сырые треки для `TrackStitcher`."""

    def __init__(self, detector: Any, tracker: str = "botsort.yaml") -> None:
        self.detector = detector
        self.tracker = tracker

    def track(self, ts: datetime, image: np.ndarray) -> list[TrackedDetection]:
        del ts  # ultralytics ведёт собственный внутренний счётчик кадров
        return raw_track(self.detector.model, image, tracker=self.tracker)


def _centroid(bbox: list[float]) -> tuple[float, float]:
    x, y, w, h = bbox
    return x + w / 2, y + h / 2


@dataclass
class _TrackState:
    stitched_id: int
    cls: str
    zone_id: str | None
    centroid: tuple[float, float]
    last_seen: datetime


class TrackStitcher:
    """Держит состояние между вызовами `update()` — один экземпляр на камеру."""

    def __init__(
        self, max_gap_seconds: float = 60.0, max_centroid_distance_px: float = 80.0
    ) -> None:
        self.max_gap_seconds = max_gap_seconds
        self.max_centroid_distance_px = max_centroid_distance_px
        self._active: dict[int, _TrackState] = {}
        self._lost: list[_TrackState] = []
        self._remap: dict[int, int] = {}
        self._next_id = 1

    def update(
        self,
        ts: datetime,
        detections: list[TrackedDetection],
        zone_of: Callable[[list[float]], str | None],
    ) -> list[TrackedDetection]:
        seen_raw_ids = set()
        stitched: list[TrackedDetection] = []

        for det in detections:
            seen_raw_ids.add(det.track_id)
            zone_id = zone_of(det.bbox)
            centroid = _centroid(det.bbox)

            stitched_id = self._remap.get(det.track_id)
            if stitched_id is None:
                stitched_id = self._match_lost(det.cls, zone_id, centroid, ts)
                if stitched_id is None:
                    stitched_id = self._next_id
                    self._next_id += 1
                self._remap[det.track_id] = stitched_id

            self._active[det.track_id] = _TrackState(stitched_id, det.cls, zone_id, centroid, ts)
            stitched.append(
                TrackedDetection(track_id=stitched_id, cls=det.cls, conf=det.conf, bbox=det.bbox)
            )

        for raw_id in list(self._active):
            if raw_id not in seen_raw_ids:
                self._lost.append(self._active.pop(raw_id))
                self._remap.pop(raw_id, None)

        self._lost = [
            lt for lt in self._lost if (ts - lt.last_seen).total_seconds() <= self.max_gap_seconds
        ]

        return stitched

    def _match_lost(
        self, cls: str, zone_id: str | None, centroid: tuple[float, float], ts: datetime
    ) -> int | None:
        best: _TrackState | None = None
        best_dist = self.max_centroid_distance_px
        for lt in self._lost:
            if lt.cls != cls:
                continue
            if (ts - lt.last_seen).total_seconds() > self.max_gap_seconds:
                continue
            if zone_id is not None and lt.zone_id is not None and zone_id != lt.zone_id:
                continue
            dx = centroid[0] - lt.centroid[0]
            dy = centroid[1] - lt.centroid[1]
            dist = (dx**2 + dy**2) ** 0.5
            if dist <= best_dist:
                best, best_dist = lt, dist
        if best is None:
            return None
        self._lost.remove(best)
        return best.stitched_id
