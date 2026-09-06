from datetime import date

import pytest

from services.analytics.machine_hours import aggregate_machine_hours, daily_quality, iter_detections


def test_iter_detections_missing_file_yields_nothing(tmp_path):
    """Регрессия: `path.open()` без проверки существования падал с
    FileNotFoundError на камере, которую ещё ни разу не опрашивали
    (services/api/scheduler.py вызывает это для каждой камеры каждую ночь)."""
    assert list(iter_detections(tmp_path / "never_polled.jsonl")) == []


def _detection(ts: str, objects: list[dict], score: float = 0.95) -> dict:
    return {
        "camera_id": "CAM-01",
        "ts": ts,
        "frame_uri": f"data/replay/CAM-01/{ts}.jpg",
        "quality": {"blur": 0.1, "night": False, "occlusion": 0.0, "score": score},
        "objects": objects,
    }


def _obj(track_id: int, cls: str, zone_id: str, state: str) -> dict:
    return {
        "track_id": track_id,
        "cls": cls,
        "conf": 0.9,
        "bbox": [0, 0, 10, 10],
        "zone_id": zone_id,
        "state": state,
        "state_conf": 0.9,
        "features": {"centroid_mad": 0.0, "area_mad": 0.0, "flow_mag": 0.0, "hsv_var": 0.0},
    }


def test_active_state_counts_toward_present_and_active():
    detections = [
        _detection("2026-09-20T07:00:00+03:00", [_obj(1, "excavator", "Z-PIT", "active")]),
        _detection("2026-09-20T07:20:00+03:00", [_obj(1, "excavator", "Z-PIT", "active")]),
    ]
    rows = aggregate_machine_hours(detections, object_id="OBJ-001", nominal_interval_sec=1200)
    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == "2026-09-20"
    assert row["zone_id"] == "Z-PIT"
    assert row["cls"] == "excavator"
    assert row["units_seen"] == 1
    # первый кадр закрывает 20 мин до второго, второй закрывает номинальный интервал (20 мин)
    assert row["mh_present"] == pytest.approx(2 / 3, abs=0.01)
    assert row["mh_active"] == row["mh_present"]
    assert row["utilization"] == 1.0


def test_idle_state_counts_present_but_not_active():
    detections = [_detection("2026-09-20T07:00:00+03:00", [_obj(1, "excavator", "Z-PIT", "idle")])]
    rows = aggregate_machine_hours(detections, object_id="OBJ-001", nominal_interval_sec=1200)
    row = rows[0]
    assert row["mh_active"] == 0.0
    assert row["mh_present"] > 0
    assert row["mh_idle"] == row["mh_present"]
    assert row["utilization"] == 0.0


def test_parked_state_excluded_entirely():
    detections = [_detection("2026-09-20T07:00:00+03:00", [_obj(1, "excavator", "Z-PIT", "parked")])]
    rows = aggregate_machine_hours(detections, object_id="OBJ-001", nominal_interval_sec=1200)
    assert rows == []


def test_unknown_state_excluded_entirely():
    detections = [_detection("2026-09-20T07:00:00+03:00", [_obj(1, "excavator", "Z-PIT", "unknown")])]
    rows = aggregate_machine_hours(detections, object_id="OBJ-001", nominal_interval_sec=1200)
    assert rows == []


def test_low_quality_frame_excluded_from_machine_hours():
    detections = [
        _detection("2026-09-20T07:00:00+03:00", [_obj(1, "excavator", "Z-PIT", "active")], score=0.3),
    ]
    rows = aggregate_machine_hours(detections, object_id="OBJ-001", nominal_interval_sec=1200)
    assert rows == []


def test_units_seen_counts_distinct_tracks():
    detections = [
        _detection(
            "2026-09-20T07:00:00+03:00",
            [
                _obj(1, "excavator", "Z-PIT", "active"),
                _obj(2, "excavator", "Z-PIT", "idle"),
            ],
        ),
    ]
    rows = aggregate_machine_hours(detections, object_id="OBJ-001", nominal_interval_sec=1200)
    assert rows[0]["units_seen"] == 2


def test_daily_quality_coverage_penalizes_bad_frames():
    detections = [
        _detection("2026-09-20T07:00:00+03:00", [], score=0.9),
        _detection("2026-09-20T07:20:00+03:00", [], score=0.2),
        _detection("2026-09-20T07:40:00+03:00", [], score=0.9),
    ]
    dq = daily_quality(detections, nominal_interval_sec=1200)
    day = dq[date(2026, 9, 20)]
    assert 0.0 < day.coverage < 1.0
    assert day.avg_quality_score == pytest.approx(0.9, abs=0.01)


def test_daily_quality_all_good_frames_full_coverage():
    detections = [
        _detection("2026-09-20T07:00:00+03:00", [], score=0.9),
        _detection("2026-09-20T07:20:00+03:00", [], score=0.9),
    ]
    dq = daily_quality(detections, nominal_interval_sec=1200)
    day = dq[date(2026, 9, 20)]
    assert day.coverage == 1.0
    assert day.confidence == pytest.approx(0.9, abs=0.01)


def test_max_gap_cap_limits_night_frame_duration():
    detections = [
        _detection("2026-09-20T07:00:00+03:00", [_obj(1, "excavator", "Z-PIT", "active")]),
        # огромный разрыв до следующего кадра — не должен "съесть" сутки целиком
        _detection("2026-09-20T22:00:00+03:00", [_obj(1, "excavator", "Z-PIT", "active")]),
    ]
    rows = aggregate_machine_hours(
        detections, object_id="OBJ-001", nominal_interval_sec=1200, max_gap_sec=3600
    )
    # 1ч (max_gap) + номинальный интервал 20 мин для последнего кадра = 1ч20мин = 1.333ч
    assert rows[0]["mh_present"] == pytest.approx(1 + 1200 / 3600, abs=0.01)


def test_multiple_zones_and_classes_produce_separate_rows():
    detections = [
        _detection(
            "2026-09-20T07:00:00+03:00",
            [
                _obj(1, "excavator", "Z-PIT", "active"),
                _obj(2, "tower_crane", "Z-FRAME", "active"),
            ],
        ),
    ]
    rows = aggregate_machine_hours(detections, object_id="OBJ-001", nominal_interval_sec=1200)
    keys = {(r["zone_id"], r["cls"]) for r in rows}
    assert keys == {("Z-PIT", "excavator"), ("Z-FRAME", "tower_crane")}


