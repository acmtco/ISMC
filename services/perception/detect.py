"""Обёртка над ultralytics YOLO — детекция техники на кадре.

Веса — результат обучения (`notebooks/`, см. `docs/04-metrics.md`), в
репозитории их нет: если файл не найден, `Detector` честно падает с понятным
сообщением (CLAUDE.md, правило 4), а не тихо скачивает generic-модель из
интернета (правило 2 — без интернета).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import yaml


@dataclass(frozen=True)
class DetectorConfig:
    weights_path: Path
    imgsz: int = 640
    conf_threshold: float = 0.35
    iou_threshold: float = 0.5
    device: str = "cpu"
    batch_size: int = 8

    @classmethod
    def from_yaml(cls, path: Path) -> DetectorConfig:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["detector"]
        return cls(
            weights_path=Path(raw["weights_path"]),
            imgsz=int(raw.get("imgsz", 640)),
            conf_threshold=float(raw.get("conf_threshold", 0.35)),
            iou_threshold=float(raw.get("iou_threshold", 0.5)),
            device=raw.get("device", "cpu"),
            batch_size=int(raw.get("batch_size", 8)),
        )


@dataclass(frozen=True)
class Detection:
    cls: str
    conf: float
    bbox: list[float]  # [x, y, w, h]


class YoloLike(Protocol):
    """Минимальный интерфейс, которого достаточно от `ultralytics.YOLO` —
    позволяет подменять модель фейком в тестах без сети и GPU."""

    names: dict[int, str]

    def __call__(self, images: list[np.ndarray], **kwargs: Any) -> list[Any]: ...


class Detector:
    """Батчевая детекция. Модель загружается лениво, только при первом вызове
    `detect()` — конструирование `Detector` не требует наличия весов."""

    def __init__(self, config: DetectorConfig, model: YoloLike | None = None) -> None:
        self.config = config
        self._model = model

    @property
    def model(self) -> YoloLike:
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def _load_model(self) -> YoloLike:
        if not self.config.weights_path.exists():
            raise FileNotFoundError(
                f"веса детектора не найдены: {self.config.weights_path}. "
                "Обучите модель (notebooks/) перед запуском — generic-модель "
                "из интернета не скачивается (CLAUDE.md, правило 2)."
            )
        from ultralytics import YOLO

        return YOLO(str(self.config.weights_path))

    def detect(self, images: list[np.ndarray]) -> list[list[Detection]]:
        """Детекции на каждое изображение, батчами по `config.batch_size`."""
        results: list[list[Detection]] = []
        for start in range(0, len(images), self.config.batch_size):
            batch = images[start : start + self.config.batch_size]
            batch_results = self.model(
                batch,
                conf=self.config.conf_threshold,
                iou=self.config.iou_threshold,
                imgsz=self.config.imgsz,
                device=self.config.device,
                verbose=False,
            )
            results.extend(_to_detections(r, self.model.names) for r in batch_results)
        return results


def _to_detections(result: Any, names: dict[int, str]) -> list[Detection]:
    detections = []
    boxes = getattr(result, "boxes", None) or []
    for box in boxes:
        x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        bbox = [x1, y1, x2 - x1, y2 - y1]
        detections.append(Detection(cls=names[cls_id], conf=conf, bbox=bbox))
    return detections


def export_onnx(weights_path: Path, imgsz: int = 640) -> Path:
    """Экспорт весов в ONNX — опционально, для ускорения инференса на CPU."""
    from ultralytics import YOLO

    model = YOLO(str(weights_path))
    exported = model.export(format="onnx", imgsz=imgsz)
    return Path(exported)
