"""Accuracy/precision/recall/F1 классификатора состояния (docs/04-metrics.md,
раздел 3). Обучение — тот же train/test сплит, что в
`services/perception/state.py::train`; здесь дополнительно снимаем
precision/recall по классам и матрицу ошибок для графика.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from services.perception.state import load_training_examples


@dataclass(frozen=True)
class ClassStateMetrics:
    state: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True)
class StateEvaluation:
    accuracy: float
    by_state: list[ClassStateMetrics]
    confusion: np.ndarray
    labels: list[str]
    n_train: int
    n_test: int


def evaluate_state_classifier(
    ground_truth_path: Path, *, test_size: float = 0.2, seed: int = 42
) -> StateEvaluation:
    x, y = load_training_examples(ground_truth_path)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=test_size, random_state=seed, stratify=y
    )
    pipeline = Pipeline([("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=1000))])
    pipeline.fit(x_train, y_train)
    y_pred = pipeline.predict(x_test)

    labels = sorted(set(y_test) | set(y_pred))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_test, y_pred, labels=labels, zero_division=0
    )
    accuracy = float((y_pred == y_test).mean())

    by_state = [
        ClassStateMetrics(
            state=label, precision=float(p), recall=float(r), f1=float(f), support=int(s)
        )
        for label, p, r, f, s in zip(labels, precision, recall, f1, support, strict=True)
    ]
    conf = confusion_matrix(y_test, y_pred, labels=labels)

    return StateEvaluation(
        accuracy=accuracy,
        by_state=by_state,
        confusion=conf,
        labels=labels,
        n_train=len(x_train),
        n_test=len(x_test),
    )
