from pathlib import Path

import numpy as np
import pytest

from services.perception.detect import Detection, Detector, DetectorConfig


class _FakeBox:
    def __init__(self, xyxy, cls_id, conf):
        self.xyxy = [np.array(xyxy, dtype=float)]
        self.cls = [cls_id]
        self.conf = [conf]


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class _FakeModel:
    """Достаточно ultralytics.YOLO-подобного интерфейса, чтобы не тянуть сеть/GPU."""

    names = {0: "excavator", 1: "dump_truck"}

    def __init__(self):
        self.calls: list[list[np.ndarray]] = []

    def __call__(self, images, **kwargs):
        self.calls.append(list(images))
        return [
            _FakeResult([_FakeBox([10, 20, 90, 140], 0, 0.87)]) for _ in images
        ]


def _config(**overrides) -> DetectorConfig:
    base = dict(
        weights_path=Path("models/does_not_exist.pt"),
        imgsz=640,
        conf_threshold=0.35,
        iou_threshold=0.5,
        device="cpu",
        batch_size=2,
    )
    base.update(overrides)
    return DetectorConfig(**base)


def test_detect_converts_boxes_to_xywh():
    model = _FakeModel()
    detector = Detector(_config(), model=model)

    images = [np.zeros((100, 100, 3), dtype=np.uint8)]
    results = detector.detect(images)

    assert len(results) == 1
    [detection] = results[0]
    assert detection == Detection(cls="excavator", conf=pytest.approx(0.87), bbox=[10, 20, 80, 120])


def test_detect_batches_according_to_config():
    model = _FakeModel()
    detector = Detector(_config(batch_size=2), model=model)

    images = [np.zeros((10, 10, 3), dtype=np.uint8) for _ in range(5)]
    detector.detect(images)

    assert [len(batch) for batch in model.calls] == [2, 2, 1]


def test_detect_passes_thresholds_to_model():
    calls: list[dict] = []

    class _SpyModel(_FakeModel):
        def __call__(self, images, **kwargs):
            calls.append(kwargs)
            return super().__call__(images, **kwargs)

    detector = Detector(_config(conf_threshold=0.42, iou_threshold=0.6), model=_SpyModel())
    detector.detect([np.zeros((10, 10, 3), dtype=np.uint8)])

    assert calls[0]["conf"] == 0.42
    assert calls[0]["iou"] == 0.6


def test_missing_weights_raise_clear_error_without_network():
    detector = Detector(_config(weights_path=Path("models/definitely_missing.pt")))
    with pytest.raises(FileNotFoundError, match="не найдены"):
        _ = detector.model
