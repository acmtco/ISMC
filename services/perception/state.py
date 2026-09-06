"""Классификатор состояния active/idle/parked.

Признаки в скользящем окне (по умолчанию 90 секунд) по треку — см. docs/02,
раздел 3, `features`: MAD смещения центроида, MAD площади бокса, средняя
величина оптического потока Фарнебака внутри бокса, дисперсия HSV-гистограммы
внутри бокса.

Модель — sklearn `LogisticRegression` (со `StandardScaler`), сохраняется в
`models/state.joblib`. Поверх модели — жёсткое правило: без движения дольше
`parked_after_hours` -> `parked`, независимо от предсказания (предсказуемость
важнее точности модели в этом крайнем случае).
"""
from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURE_NAMES = ["centroid_mad", "area_mad", "flow_mag", "hsv_var"]

# Ниже этого MAD трек считается неподвижным для правила "parked".
MOVEMENT_EPS = 0.5

EDGE_IMI_F1_REFERENCE = 0.76  # ориентир из литературы (bbox-признаки, без потока)


# ---------------------------------------------------------------------------
# Извлечение признаков в реальном времени (для pipeline.py)
# ---------------------------------------------------------------------------


@dataclass
class _TrackWindow:
    centroids: deque = field(default_factory=deque)
    areas: deque = field(default_factory=deque)
    timestamps: deque = field(default_factory=deque)
    last_movement_ts: datetime | None = None


def _mad(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    arr = np.array(values)
    return float(np.median(np.abs(arr - np.median(arr))))


class FeatureTracker:
    """Скользящее окно признаков движения по track_id."""

    def __init__(self, window_sec: float = 90.0) -> None:
        self.window_sec = window_sec
        self._windows: dict[int, _TrackWindow] = {}

    def update(self, track_id: int, ts: datetime, bbox: list[float]) -> dict:
        window = self._windows.setdefault(track_id, _TrackWindow())
        x, y, w, h = bbox
        centroid = (x + w / 2, y + h / 2)
        area = w * h

        window.centroids.append(centroid)
        window.areas.append(area)
        window.timestamps.append(ts)

        cutoff = ts - timedelta(seconds=self.window_sec)
        while window.timestamps and window.timestamps[0] < cutoff:
            window.timestamps.popleft()
            window.centroids.popleft()
            window.areas.popleft()

        centroid_mad = (
            _mad([c[0] for c in window.centroids]) + _mad([c[1] for c in window.centroids])
        ) / 2
        area_mad = _mad(list(window.areas))

        if centroid_mad > MOVEMENT_EPS or area_mad > MOVEMENT_EPS:
            window.last_movement_ts = ts

        seconds_since_movement = (
            (ts - window.last_movement_ts).total_seconds()
            if window.last_movement_ts is not None
            else None
        )

        return {
            "centroid_mad": round(centroid_mad, 2),
            "area_mad": round(area_mad, 2),
            "seconds_since_movement": seconds_since_movement,
        }

    def forget(self, track_id: int) -> None:
        self._windows.pop(track_id, None)


def crop(image: np.ndarray, bbox: list[float]) -> np.ndarray:
    x, y, w, h = (int(round(v)) for v in bbox)
    img_h, img_w = image.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, img_w), min(y + h, img_h)
    if x1 <= x0 or y1 <= y0:
        return image[0:0, 0:0]
    return image[y0:y1, x0:x1]


def optical_flow_magnitude(prev_gray_crop: np.ndarray, gray_crop: np.ndarray) -> float:
    """Средняя величина оптического потока Фарнебака внутри бокса."""
    if prev_gray_crop.shape != gray_crop.shape or prev_gray_crop.size == 0:
        return 0.0
    flow = cv2.calcOpticalFlowFarneback(prev_gray_crop, gray_crop, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    return float(magnitude.mean())


def hsv_variance(bgr_crop: np.ndarray) -> float:
    """Пространственная дисперсия H/S/V внутри бокса (текстура/изменчивость).

    Дисперсия считается отдельно по каждому каналу и суммируется — иначе
    для идеально однородного (но не серого) пятна variance по всему массиву
    была бы ненулевой просто из-за разницы средних уровней H/S/V, а не из-за
    текстуры внутри бокса.
    """
    if bgr_crop.size == 0:
        return 0.0
    hsv = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2HSV).astype(np.float32)
    channel_variances = hsv.reshape(-1, 3).var(axis=0)
    return float(channel_variances.sum())


# ---------------------------------------------------------------------------
# Классификатор
# ---------------------------------------------------------------------------


class StateClassifier:
    def __init__(self, pipeline: Pipeline, parked_after_hours: float = 2.0) -> None:
        self.pipeline = pipeline
        self.parked_after_hours = parked_after_hours

    def predict(
        self, features: dict, seconds_since_movement: float | None = None
    ) -> tuple[str, float]:
        if (
            seconds_since_movement is not None
            and seconds_since_movement >= self.parked_after_hours * 3600
        ):
            return "parked", 1.0

        x = np.array([[features.get(name, 0.0) for name in FEATURE_NAMES]])
        proba = self.pipeline.predict_proba(x)[0]
        best_idx = int(np.argmax(proba))
        return str(self.pipeline.classes_[best_idx]), float(proba[best_idx])

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        payload = {"pipeline": self.pipeline, "parked_after_hours": self.parked_after_hours}
        joblib.dump(payload, path)

    @classmethod
    def load(cls, path: Path) -> StateClassifier:
        payload = joblib.load(path)
        return cls(payload["pipeline"], payload["parked_after_hours"])


# ---------------------------------------------------------------------------
# Обучение на ground_truth.jsonl синтетического бенчмарка
# ---------------------------------------------------------------------------


def load_training_examples(ground_truth_path: Path) -> tuple[np.ndarray, np.ndarray]:
    xs: list[list[float]] = []
    ys: list[str] = []
    with Path(ground_truth_path).open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            for obj in record["objects"]:
                features = obj["features"]
                xs.append([features.get(name, 0.0) for name in FEATURE_NAMES])
                ys.append(obj["state"])
    return np.array(xs), np.array(ys)


@dataclass
class TrainMetrics:
    accuracy: float
    f1_macro: float
    f1_by_class: dict[str, float]
    report: str
    n_train: int
    n_test: int


def train(
    ground_truth_path: Path,
    model_path: Path,
    *,
    parked_after_hours: float = 2.0,
    test_size: float = 0.2,
    seed: int = 42,
) -> TrainMetrics:
    x, y = load_training_examples(ground_truth_path)
    if len(x) == 0:
        raise ValueError(f"в {ground_truth_path} нет объектов для обучения")

    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=test_size, random_state=seed, stratify=y
    )

    pipeline = Pipeline(
        [("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=1000))]
    )
    pipeline.fit(x_train, y_train)

    y_pred = pipeline.predict(x_test)
    labels = list(pipeline.classes_)
    f1_per_label = f1_score(y_test, y_pred, average=None, labels=labels)

    f1_by_class = dict(
        zip((str(v) for v in labels), (float(v) for v in f1_per_label), strict=True)
    )
    metrics = TrainMetrics(
        accuracy=float(accuracy_score(y_test, y_pred)),
        f1_macro=float(f1_score(y_test, y_pred, average="macro")),
        f1_by_class=f1_by_class,
        report=classification_report(y_test, y_pred),
        n_train=len(x_train),
        n_test=len(x_test),
    )

    StateClassifier(pipeline, parked_after_hours=parked_after_hours).save(model_path)
    return metrics


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ground-truth", type=Path, default=Path("data/benchmark/ground_truth.jsonl")
    )
    parser.add_argument("--model-out", type=Path, default=Path("models/state.joblib"))
    parser.add_argument("--parked-after-hours", type=float, default=2.0)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    metrics = train(
        args.ground_truth,
        args.model_out,
        parked_after_hours=args.parked_after_hours,
        test_size=args.test_size,
        seed=args.seed,
    )
    print(f"Обучено на {metrics.n_train} примерах, проверено на {metrics.n_test}")
    print(f"Accuracy: {metrics.accuracy:.3f}")
    print(
        f"F1 (macro): {metrics.f1_macro:.3f}  "
        f"(ориентир Edge-IMI, bbox-признаки: {EDGE_IMI_F1_REFERENCE})"
    )
    for cls_name, f1 in metrics.f1_by_class.items():
        print(f"  F1 ({cls_name}): {f1:.3f}")
    print()
    print(metrics.report)
    print(f"Модель сохранена: {args.model_out}")


if __name__ == "__main__":
    main()
