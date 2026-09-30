"""mAP@50 / mAP@50-95 по классам (docs/04-metrics.md, раздел 1).

Считается только если есть обученные веса детектора — без них раздел честно
помечается "нет данных", а не подделывается (docs/01-principles.md, правило 4). Формулы
(AP через непрерывную интерполяцию precision/recall, IoU-сопоставление) не
зависят от весов и покрыты тестами на игрушечных боксах отдельно.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from services.perception.detect import Detector, DetectorConfig


def iou(box_a: list[float], box_b: list[float]) -> float:
    """box = [x, y, w, h]."""
    ax0, ay0, ax1, ay1 = box_a[0], box_a[1], box_a[0] + box_a[2], box_a[1] + box_a[3]
    bx0, by0, bx1, by1 = box_b[0], box_b[1], box_b[0] + box_b[2], box_b[1] + box_b[3]
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_a = max(0.0, box_a[2]) * max(0.0, box_a[3])
    area_b = max(0.0, box_b[2]) * max(0.0, box_b[3])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass(frozen=True)
class Detection:
    cls: str
    conf: float
    bbox: list[float]


@dataclass(frozen=True)
class GroundTruthBox:
    cls: str
    bbox: list[float]


def average_precision(recalls: np.ndarray, precisions: np.ndarray) -> float:
    """Непрерывная (all-point) интерполяция площади под кривой P/R — тот же
    метод, что использует COCO."""
    recalls = np.concatenate(([0.0], recalls, [1.0]))
    precisions = np.concatenate(([0.0], precisions, [0.0]))
    for i in range(len(precisions) - 2, -1, -1):
        precisions[i] = max(precisions[i], precisions[i + 1])
    indices = np.where(recalls[1:] != recalls[:-1])[0]
    return float(np.sum((recalls[indices + 1] - recalls[indices]) * precisions[indices + 1]))


def average_precision_at_iou(
    predictions_by_frame: list[list[Detection]],
    ground_truth_by_frame: list[list[GroundTruthBox]],
    cls: str,
    iou_threshold: float,
) -> float | None:
    """AP одного класса на одном пороге IoU. None, если в GT нет объектов класса."""
    scored: list[tuple[float, int, int]] = []
    for frame_idx, dets in enumerate(predictions_by_frame):
        for det_idx, det in enumerate(dets):
            if det.cls == cls:
                scored.append((det.conf, frame_idx, det_idx))
    scored.sort(key=lambda t: -t[0])

    n_gt = sum(1 for gts in ground_truth_by_frame for gt in gts if gt.cls == cls)
    if n_gt == 0:
        return None

    matched_gt: list[set[int]] = [set() for _ in ground_truth_by_frame]
    tp = np.zeros(len(scored))
    fp = np.zeros(len(scored))

    for rank, (_conf, frame_idx, det_idx) in enumerate(scored):
        det = predictions_by_frame[frame_idx][det_idx]
        gts = [(i, gt) for i, gt in enumerate(ground_truth_by_frame[frame_idx]) if gt.cls == cls]
        best_iou, best_gt_idx = 0.0, -1
        for gt_idx, gt in gts:
            if gt_idx in matched_gt[frame_idx]:
                continue
            v = iou(det.bbox, gt.bbox)
            if v > best_iou:
                best_iou, best_gt_idx = v, gt_idx
        if best_iou >= iou_threshold and best_gt_idx >= 0:
            matched_gt[frame_idx].add(best_gt_idx)
            tp[rank] = 1
        else:
            fp[rank] = 1

    tp_cum = np.cumsum(tp)
    fp_cum = np.cumsum(fp)
    recalls = tp_cum / n_gt
    precisions = tp_cum / np.maximum(tp_cum + fp_cum, 1e-9)
    return average_precision(recalls, precisions)


@dataclass(frozen=True)
class ClassDetectionMetrics:
    cls: str
    n_images: int
    map50: float | None
    map50_95: float | None
    precision: float | None
    recall: float | None


IOU_THRESHOLDS_50_95 = np.linspace(0.5, 0.95, 10)


def evaluate_detection(
    predictions_by_frame: list[list[Detection]],
    ground_truth_by_frame: list[list[GroundTruthBox]],
    classes: list[str],
    conf_threshold: float = 0.35,
) -> list[ClassDetectionMetrics]:
    results = []
    for cls in classes:
        n_images = sum(1 for gts in ground_truth_by_frame if any(gt.cls == cls for gt in gts))
        ap50 = average_precision_at_iou(predictions_by_frame, ground_truth_by_frame, cls, 0.5)
        aps = [
            average_precision_at_iou(predictions_by_frame, ground_truth_by_frame, cls, t)
            for t in IOU_THRESHOLDS_50_95
        ]
        aps_valid = [a for a in aps if a is not None]
        map50_95 = float(np.mean(aps_valid)) if aps_valid else None

        precision, recall = _precision_recall_at_threshold(
            predictions_by_frame, ground_truth_by_frame, cls, conf_threshold
        )
        results.append(
            ClassDetectionMetrics(
                cls=cls,
                n_images=n_images,
                map50=ap50,
                map50_95=map50_95,
                precision=precision,
                recall=recall,
            )
        )
    return results


def _precision_recall_at_threshold(
    predictions_by_frame: list[list[Detection]],
    ground_truth_by_frame: list[list[GroundTruthBox]],
    cls: str,
    conf_threshold: float,
) -> tuple[float | None, float | None]:
    tp = fp = fn = 0
    for frame_idx, gts in enumerate(ground_truth_by_frame):
        gt_cls = [g for g in gts if g.cls == cls]
        dets = [
            d for d in predictions_by_frame[frame_idx] if d.cls == cls and d.conf >= conf_threshold
        ]
        matched: set[int] = set()
        for det in dets:
            best_iou, best_idx = 0.0, -1
            for i, gt in enumerate(gt_cls):
                if i in matched:
                    continue
                v = iou(det.bbox, gt.bbox)
                if v > best_iou:
                    best_iou, best_idx = v, i
            if best_iou >= 0.5 and best_idx >= 0:
                matched.add(best_idx)
                tp += 1
            else:
                fp += 1
        fn += len(gt_cls) - len(matched)

    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    return precision, recall


def run_detector_evaluation(
    *,
    detector_config_path: Path,
    ground_truth_path: Path,
    classes: list[str],
) -> list[ClassDetectionMetrics] | None:
    """None, если весов детектора нет — раздел 1 отчёта тогда честно пуст."""
    config = DetectorConfig.from_yaml(detector_config_path)
    if not config.weights_path.exists():
        return None

    detector = Detector(config)
    predictions_by_frame: list[list[Detection]] = []
    ground_truth_by_frame: list[list[GroundTruthBox]] = []

    from PIL import Image

    with Path(ground_truth_path).open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            image = np.array(Image.open(record["frame_uri"]).convert("RGB"))[:, :, ::-1]
            [dets] = detector.detect([image])
            predictions_by_frame.append([Detection(d.cls, d.conf, d.bbox) for d in dets])
            ground_truth_by_frame.append(
                [GroundTruthBox(o["cls"], o["bbox"]) for o in record["objects"]]
            )

    return evaluate_detection(predictions_by_frame, ground_truth_by_frame, classes)
