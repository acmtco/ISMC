from datetime import datetime, timedelta

from services.perception.track import TrackedDetection, TrackStitcher

BASE = datetime(2026, 1, 1, 12, 0, 0)


def _no_zone(_bbox):
    return "Z-A"


def test_stable_raw_id_keeps_same_stitched_id():
    stitcher = TrackStitcher(max_gap_seconds=60)
    det = TrackedDetection(track_id=7, cls="excavator", conf=0.9, bbox=[10, 10, 20, 20])

    first = stitcher.update(BASE, [det], _no_zone)
    second = stitcher.update(BASE + timedelta(seconds=5), [det], _no_zone)

    assert first[0].track_id == second[0].track_id


def test_short_gap_reuses_track_id():
    stitcher = TrackStitcher(max_gap_seconds=60, max_centroid_distance_px=50)
    det_a = TrackedDetection(track_id=1, cls="excavator", conf=0.9, bbox=[100, 100, 20, 20])
    out_a = stitcher.update(BASE, [det_a], _no_zone)

    # трек пропал на 40с, BoT-SORT переоткрыл его с новым сырым id рядом
    stitcher.update(BASE + timedelta(seconds=20), [], _no_zone)
    det_b = TrackedDetection(track_id=2, cls="excavator", conf=0.9, bbox=[105, 103, 20, 20])
    out_b = stitcher.update(BASE + timedelta(seconds=40), [det_b], _no_zone)

    assert out_b[0].track_id == out_a[0].track_id


def test_long_gap_does_not_stitch():
    stitcher = TrackStitcher(max_gap_seconds=60, max_centroid_distance_px=50)
    det_a = TrackedDetection(track_id=1, cls="excavator", conf=0.9, bbox=[100, 100, 20, 20])
    out_a = stitcher.update(BASE, [det_a], _no_zone)

    stitcher.update(BASE + timedelta(seconds=30), [], _no_zone)
    det_b = TrackedDetection(track_id=2, cls="excavator", conf=0.9, bbox=[102, 101, 20, 20])
    out_b = stitcher.update(BASE + timedelta(seconds=90), [det_b], _no_zone)

    assert out_b[0].track_id != out_a[0].track_id


def test_different_class_does_not_stitch():
    stitcher = TrackStitcher(max_gap_seconds=60, max_centroid_distance_px=50)
    det_a = TrackedDetection(track_id=1, cls="excavator", conf=0.9, bbox=[100, 100, 20, 20])
    out_a = stitcher.update(BASE, [det_a], _no_zone)

    stitcher.update(BASE + timedelta(seconds=10), [], _no_zone)
    det_b = TrackedDetection(track_id=2, cls="dump_truck", conf=0.9, bbox=[101, 100, 20, 20])
    out_b = stitcher.update(BASE + timedelta(seconds=20), [det_b], _no_zone)

    assert out_b[0].track_id != out_a[0].track_id


def test_far_away_detection_does_not_stitch():
    stitcher = TrackStitcher(max_gap_seconds=60, max_centroid_distance_px=30)
    det_a = TrackedDetection(track_id=1, cls="excavator", conf=0.9, bbox=[100, 100, 20, 20])
    out_a = stitcher.update(BASE, [det_a], _no_zone)

    stitcher.update(BASE + timedelta(seconds=10), [], _no_zone)
    det_b = TrackedDetection(track_id=2, cls="excavator", conf=0.9, bbox=[500, 500, 20, 20])
    out_b = stitcher.update(BASE + timedelta(seconds=20), [det_b], _no_zone)

    assert out_b[0].track_id != out_a[0].track_id
