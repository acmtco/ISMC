import pytest

from scripts.eval.detection_metrics import (
    Detection,
    GroundTruthBox,
    average_precision,
    average_precision_at_iou,
    evaluate_detection,
    iou,
)


def test_iou_identical_boxes_is_one():
    box = [10, 10, 20, 20]
    assert iou(box, box) == pytest.approx(1.0)


def test_iou_disjoint_boxes_is_zero():
    assert iou([0, 0, 10, 10], [100, 100, 10, 10]) == 0.0


def test_iou_half_overlap():
    a = [0, 0, 10, 10]
    b = [5, 0, 10, 10]
    # intersection 5x10=50, union 100+100-50=150
    assert iou(a, b) == pytest.approx(50 / 150)


def test_average_precision_perfect_curve_is_one():
    import numpy as np

    recalls = np.array([0.5, 1.0])
    precisions = np.array([1.0, 1.0])
    assert average_precision(recalls, precisions) == pytest.approx(1.0)


def test_average_precision_no_detections_is_zero():
    import numpy as np

    assert average_precision(np.array([0.0]), np.array([0.0])) == pytest.approx(0.0)


def test_average_precision_at_iou_perfect_match():
    preds = [[Detection(cls="excavator", conf=0.9, bbox=[10, 10, 20, 20])]]
    gts = [[GroundTruthBox(cls="excavator", bbox=[10, 10, 20, 20])]]
    ap = average_precision_at_iou(preds, gts, "excavator", 0.5)
    assert ap == pytest.approx(1.0)


def test_average_precision_at_iou_no_ground_truth_returns_none():
    preds = [[Detection(cls="excavator", conf=0.9, bbox=[10, 10, 20, 20])]]
    gts = [[]]
    assert average_precision_at_iou(preds, gts, "excavator", 0.5) is None


def test_average_precision_at_iou_false_positive_hurts_precision():
    # ложное срабатывание должно идти ПЕРВЫМ по уверенности — иначе recall=1.0
    # уже достигнут true positive'ом раньше, и последующий FP на AP не влияет
    # (стандартное поведение AP через непрерывную интерполяцию, как в COCO).
    preds = [
        [
            Detection(cls="excavator", conf=0.95, bbox=[200, 200, 20, 20]),  # мимо
            Detection(cls="excavator", conf=0.9, bbox=[10, 10, 20, 20]),
        ]
    ]
    gts = [[GroundTruthBox(cls="excavator", bbox=[10, 10, 20, 20])]]
    ap = average_precision_at_iou(preds, gts, "excavator", 0.5)
    assert ap is not None
    assert ap < 1.0


def test_average_precision_at_iou_missed_detection_hurts_recall():
    preds = [[]]
    gts = [[GroundTruthBox(cls="excavator", bbox=[10, 10, 20, 20])]]
    ap = average_precision_at_iou(preds, gts, "excavator", 0.5)
    assert ap == pytest.approx(0.0)


def test_evaluate_detection_per_class_metrics():
    preds = [
        [Detection(cls="excavator", conf=0.95, bbox=[10, 10, 20, 20])],
        [Detection(cls="excavator", conf=0.4, bbox=[500, 500, 20, 20])],  # ложное срабатывание
    ]
    gts = [
        [GroundTruthBox(cls="excavator", bbox=[10, 10, 20, 20])],
        [GroundTruthBox(cls="excavator", bbox=[50, 50, 20, 20])],  # пропущено
    ]
    [metrics] = evaluate_detection(preds, gts, ["excavator"], conf_threshold=0.35)
    assert metrics.cls == "excavator"
    assert metrics.n_images == 2
    assert metrics.map50 is not None
    assert 0.0 < metrics.map50 < 1.0
    assert metrics.precision == pytest.approx(0.5)  # 1 tp, 1 fp
    assert metrics.recall == pytest.approx(0.5)  # 1 tp, 1 fn


def test_evaluate_detection_class_absent_from_ground_truth():
    preds = [[]]
    gts = [[]]
    [metrics] = evaluate_detection(preds, gts, ["excavator"])
    assert metrics.map50 is None
    assert metrics.map50_95 is None
    assert metrics.precision is None
    assert metrics.recall is None
