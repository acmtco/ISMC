import pytest

from scripts.eval.tracking_metrics import TrackedBox, compute_tracking_metrics


def test_perfect_tracking_gives_mota_and_idf1_one():
    gt = [
        [TrackedBox(track_id=1, bbox=[0, 0, 10, 10])],
        [TrackedBox(track_id=1, bbox=[1, 0, 10, 10])],
        [TrackedBox(track_id=1, bbox=[2, 0, 10, 10])],
    ]
    pred = [
        [TrackedBox(track_id=101, bbox=[0, 0, 10, 10])],
        [TrackedBox(track_id=101, bbox=[1, 0, 10, 10])],
        [TrackedBox(track_id=101, bbox=[2, 0, 10, 10])],
    ]
    metrics = compute_tracking_metrics(gt, pred)
    assert metrics.mota == pytest.approx(1.0)
    assert metrics.idf1 == pytest.approx(1.0)
    assert metrics.id_switches == 0
    assert metrics.num_frames == 3


def test_id_switch_is_counted():
    gt = [
        [TrackedBox(track_id=1, bbox=[0, 0, 10, 10])],
        [TrackedBox(track_id=1, bbox=[1, 0, 10, 10])],
        [TrackedBox(track_id=1, bbox=[2, 0, 10, 10])],
    ]
    # предсказанный id меняется на середине трека — типичный разрыв трекера
    pred = [
        [TrackedBox(track_id=101, bbox=[0, 0, 10, 10])],
        [TrackedBox(track_id=101, bbox=[1, 0, 10, 10])],
        [TrackedBox(track_id=202, bbox=[2, 0, 10, 10])],
    ]
    metrics = compute_tracking_metrics(gt, pred)
    assert metrics.id_switches == 1
    assert metrics.mota < 1.0 or metrics.idf1 < 1.0


def test_missed_detection_lowers_mota():
    gt = [
        [TrackedBox(track_id=1, bbox=[0, 0, 10, 10])],
        [TrackedBox(track_id=1, bbox=[1, 0, 10, 10])],
    ]
    pred = [
        [TrackedBox(track_id=101, bbox=[0, 0, 10, 10])],
        [],  # трекер потерял объект
    ]
    metrics = compute_tracking_metrics(gt, pred)
    assert metrics.mota < 1.0


def test_false_positive_lowers_mota():
    gt = [[TrackedBox(track_id=1, bbox=[0, 0, 10, 10])]]
    pred = [
        [
            TrackedBox(track_id=101, bbox=[0, 0, 10, 10]),
            TrackedBox(track_id=202, bbox=[500, 500, 10, 10]),  # лишний объект
        ]
    ]
    metrics = compute_tracking_metrics(gt, pred)
    assert metrics.mota < 1.0


def test_empty_frames_do_not_crash():
    metrics = compute_tracking_metrics([[]], [[]])
    assert metrics.num_frames == 1
