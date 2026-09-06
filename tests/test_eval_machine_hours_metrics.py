import pytest

from scripts.eval.machine_hours_metrics import evaluate_machine_hours

QUALITY_OK = {"blur": 0.1, "night": False, "occlusion": 0.0, "score": 0.95}


def _record(ts: str, track_id: int, cls: str, zone_id: str, state: str) -> dict:
    return {
        "camera_id": "CAM-01",
        "ts": ts,
        "frame_uri": f"{ts}.jpg",
        "quality": QUALITY_OK,
        "objects": [
            {
                "track_id": track_id,
                "cls": cls,
                "conf": 0.9,
                "bbox": [0, 0, 10, 10],
                "zone_id": zone_id,
                "state": state,
                "state_conf": 0.9,
                "features": {"centroid_mad": 0.0, "area_mad": 0.0, "flow_mag": 0.0, "hsv_var": 0.0},
            }
        ],
    }


def test_identical_predictions_have_zero_error():
    records = [
        _record("2026-09-20T07:00:00+03:00", 1, "excavator", "Z-PIT", "active"),
        _record("2026-09-20T07:20:00+03:00", 1, "excavator", "Z-PIT", "active"),
    ]
    result = evaluate_machine_hours(records, records, object_id="OBJ-001")
    assert result.mae_active_hours == pytest.approx(0.0)
    assert result.mape_active_pct == pytest.approx(0.0)
    assert result.bias_active_hours == pytest.approx(0.0)


def test_predicted_idle_when_truth_active_creates_error():
    truth = [
        _record("2026-09-20T07:00:00+03:00", 1, "excavator", "Z-PIT", "active"),
        _record("2026-09-20T07:20:00+03:00", 1, "excavator", "Z-PIT", "active"),
    ]
    predicted = [
        _record("2026-09-20T07:00:00+03:00", 1, "excavator", "Z-PIT", "idle"),
        _record("2026-09-20T07:20:00+03:00", 1, "excavator", "Z-PIT", "idle"),
    ]
    result = evaluate_machine_hours(predicted, truth, object_id="OBJ-001")
    assert result.mae_active_hours > 0
    assert result.mape_active_pct == pytest.approx(100.0, abs=0.5)  # факт активности упал до нуля
    assert result.bias_active_hours < 0  # предсказание занижает mh_active


def test_predicted_active_when_truth_idle_gives_positive_bias():
    truth = [_record("2026-09-20T07:00:00+03:00", 1, "excavator", "Z-PIT", "idle")]
    predicted = [_record("2026-09-20T07:00:00+03:00", 1, "excavator", "Z-PIT", "active")]
    result = evaluate_machine_hours(predicted, truth, object_id="OBJ-001")
    assert result.bias_active_hours > 0


def test_missing_dates_in_prediction_still_compared():
    truth = [
        _record("2026-09-20T07:00:00+03:00", 1, "excavator", "Z-PIT", "active"),
        _record("2026-09-21T07:00:00+03:00", 1, "excavator", "Z-PIT", "active"),
    ]
    predicted = [_record("2026-09-20T07:00:00+03:00", 1, "excavator", "Z-PIT", "active")]
    result = evaluate_machine_hours(predicted, truth, object_id="OBJ-001")
    assert result.n_rows == 2  # два (дата, зона, класс) ключа — второй день предсказание "0"
    assert result.mae_active_hours > 0
