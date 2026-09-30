"""Источники кадров: RTSP/HLS (`live`) и папка/replay (`replay`).

Смена режима — `HG_MODE` + `source.kind` в `objects.json`, не правка кода
(docs/01-principles.md, правило 3). Общий интерфейс — `FrameSource.iter_frames()`,
отдающий `(ts, image)` в порядке съёмки.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

MSK = timezone(timedelta(hours=3))


@dataclass
class Frame:
    ts: datetime
    image: np.ndarray  # BGR, как в cv2
    uri: str | None = None


class FrameSource(ABC):
    @abstractmethod
    def iter_frames(self) -> Iterator[Frame]:
        """Итератор кадров в хронологическом порядке."""


class FolderSource(FrameSource):
    """Кадры из папки с именами `<YYYYMMDDTHHMMSS>.jpg` (docs/02, раздел 3)."""

    def __init__(self, path: Path, pattern: str = "*.jpg", tz: timezone = MSK) -> None:
        self.path = Path(path)
        self.pattern = pattern
        self.tz = tz

    def iter_frames(self) -> Iterator[Frame]:
        for file in sorted(self.path.glob(self.pattern)):
            image = cv2.imread(str(file))
            if image is None:
                raise ValueError(f"не удалось прочитать кадр: {file}")
            yield Frame(ts=self._parse_ts(file.stem), image=image, uri=file.as_posix())

    def _parse_ts(self, stem: str) -> datetime:
        naive = datetime.strptime(stem, "%Y%m%dT%H%M%S")
        return naive.replace(tzinfo=self.tz)


class ReplaySource(FrameSource):
    """`FolderSource` с опциональным воспроизведением в реальном времени.

    `speed=None` — кадры отдаются без задержек (пакетная обработка, оценка).
    `speed=N` — пауза между кадрами = (реальный интервал между их метками
    времени) / N: имитация "машины времени" для живой демонстрации.
    """

    def __init__(
        self,
        path: Path,
        pattern: str = "*.jpg",
        tz: timezone = MSK,
        speed: float | None = None,
    ) -> None:
        self._folder = FolderSource(path, pattern=pattern, tz=tz)
        self.speed = speed

    def iter_frames(self) -> Iterator[Frame]:
        prev_ts: datetime | None = None
        for frame in self._folder.iter_frames():
            if self.speed and prev_ts is not None:
                delay = (frame.ts - prev_ts).total_seconds() / self.speed
                if delay > 0:
                    time.sleep(delay)
            prev_ts = frame.ts
            yield frame


class RtspSource(FrameSource):
    """Живая камера через `cv2.VideoCapture` (RTSP)."""

    def __init__(self, uri: str, tz: timezone = MSK) -> None:
        self.uri = uri
        self.tz = tz

    def iter_frames(self) -> Iterator[Frame]:
        cap = cv2.VideoCapture(self.uri)
        if not cap.isOpened():
            raise ConnectionError(f"не удалось открыть поток: {self.uri}")
        try:
            while True:
                ok, image = cap.read()
                if not ok:
                    break
                yield Frame(ts=datetime.now(self.tz), image=image, uri=self.uri)
        finally:
            cap.release()


class HlsSource(RtspSource):
    """HLS открывается тем же `cv2.VideoCapture`; отдельный класс — для ясности
    контракта (`source.kind == "hls"`), поведение идентично `RtspSource`."""


def open_source(
    camera_source: dict, *, tz: timezone = MSK, replay_speed: float | None = None
) -> FrameSource:
    """Фабрика по `objects.json[*].cameras[*].source` (docs/02, раздел 1)."""
    kind = camera_source["kind"]
    uri = camera_source["uri"]
    if kind == "folder":
        return FolderSource(Path(uri), tz=tz)
    if kind == "replay":
        return ReplaySource(Path(uri), tz=tz, speed=replay_speed)
    if kind == "rtsp":
        return RtspSource(uri, tz=tz)
    if kind == "hls":
        return HlsSource(uri, tz=tz)
    raise ValueError(f"неизвестный тип источника: {kind!r}")
