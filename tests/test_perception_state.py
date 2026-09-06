from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from scripts.make_synthetic import generate
from scripts.synth.scenario import load_scenario
from services.perception.state import (
    EDGE_IMI_F1_REFERENCE,
    FeatureTracker,
    StateClassifier,
    crop,
    hsv_variance,
    optical_flow_magnitude,
    train,
)

BASE = datetime(2026, 1, 1, 7, 0, 0)


def test_feature_tracker_stationary_track_has_low_mad():
    tracker = FeatureTracker(window_sec=90)
    bbox = [100, 100, 20, 20]
    result = None
    for i in range(5):
        result = tracker.update(track_id=1, ts=BASE + timedelta(seconds=i * 10), bbox=bbox)
    assert result["centroid_mad"] == 0.0
    assert result["area_mad"] == 0.0


def test_feature_tracker_moving_track_has_higher_mad():
    tracker = FeatureTracker(window_sec=90)
    result = None
    for i in range(6):
        bbox = [100 + i * 15, 100, 20, 20]
        result = tracker.update(track_id=2, ts=BASE + timedelta(seconds=i * 10), bbox=bbox)
    assert result["centroid_mad"] > 1.0


def test_feature_tracker_window_expires_old_points():
    tracker = FeatureTracker(window_sec=30)
    tracker.update(track_id=3, ts=BASE, bbox=[0, 0, 10, 10])
    tracker.update(track_id=3, ts=BASE + timedelta(seconds=10), bbox=[50, 0, 10, 10])
    # этот кадр вне окна 30с относительно первого — старая точка должна выпасть
    result = tracker.update(track_id=3, ts=BASE + timedelta(seconds=45), bbox=[50, 0, 10, 10])
    assert result["centroid_mad"] == 0.0


def test_feature_tracker_seconds_since_movement_tracks_stillness():
    tracker = FeatureTracker(window_sec=90)
    tracker.update(track_id=4, ts=BASE, bbox=[0, 0, 10, 10])
    tracker.update(track_id=4, ts=BASE + timedelta(seconds=50), bbox=[100, 0, 10, 10])
    result = tracker.update(track_id=4, ts=BASE + timedelta(seconds=100), bbox=[100, 0, 10, 10])
    assert result["seconds_since_movement"] == pytest.approx(50.0, abs=1.0)


def test_crop_clips_to_image_bounds():
    image = np.zeros((50, 50, 3), dtype=np.uint8)
    out = crop(image, [40, 40, 30, 30])
    assert out.shape == (10, 10, 3)


def test_crop_out_of_bounds_returns_empty():
    image = np.zeros((50, 50, 3), dtype=np.uint8)
    out = crop(image, [100, 100, 10, 10])
    assert out.size == 0


def test_optical_flow_magnitude_zero_for_identical_frames():
    gray = np.random.default_rng(0).integers(0, 255, (40, 40), dtype=np.uint8)
    assert optical_flow_magnitude(gray, gray) == pytest.approx(0.0, abs=0.05)


def test_optical_flow_magnitude_empty_crop_is_zero():
    empty = np.zeros((0, 0), dtype=np.uint8)
    assert optical_flow_magnitude(empty, empty) == 0.0


def test_hsv_variance_uniform_crop_is_zero():
    solid = np.full((20, 20, 3), 128, dtype=np.uint8)
    assert hsv_variance(solid) == pytest.approx(0.0, abs=1e-6)


def test_hsv_variance_empty_crop_is_zero():
    assert hsv_variance(np.zeros((0, 0, 3), dtype=np.uint8)) == 0.0


@pytest.fixture(scope="module")
def synthetic_ground_truth(tmp_path_factory):
    scenario = load_scenario(Path("data/ref/scenario_demo.yaml"))
    tmp_path = tmp_path_factory.mktemp("state_gt")
    generate(
        scenario,
        days=10,
        sprites_dir=tmp_path / "sprites",
        out_dir=tmp_path / "frames",
        benchmark_dir=tmp_path / "bench",
    )
    return tmp_path / "bench" / "ground_truth.jsonl"


def test_train_beats_edge_imi_reference_on_synthetic_labels(synthetic_ground_truth, tmp_path):
    metrics = train(synthetic_ground_truth, tmp_path / "state.joblib", seed=42)

    print(f"\naccuracy={metrics.accuracy:.3f} f1_macro={metrics.f1_macro:.3f}")
    assert metrics.n_train > 0
    assert metrics.n_test > 0
    assert metrics.accuracy > 0.8
    assert metrics.f1_macro > EDGE_IMI_F1_REFERENCE


def test_state_classifier_predict_returns_known_state(synthetic_ground_truth, tmp_path):
    model_path = tmp_path / "state2.joblib"
    train(synthetic_ground_truth, model_path, seed=42)
    classifier = StateClassifier.load(model_path)

    state, conf = classifier.predict(
        {"centroid_mad": 5.0, "area_mad": 300.0, "flow_mag": 2.0, "hsv_var": 600.0}
    )
    assert state in {"active", "idle", "parked"}
    assert 0.0 <= conf <= 1.0


def test_parked_rule_overrides_model_after_threshold(synthetic_ground_truth, tmp_path):
    model_path = tmp_path / "state3.joblib"
    train(synthetic_ground_truth, model_path, parked_after_hours=2.0, seed=42)
    classifier = StateClassifier.load(model_path)

    # признаки как у активной техники, но неподвижна больше 2 часов -> parked
    state, conf = classifier.predict(
        {"centroid_mad": 5.0, "area_mad": 300.0, "flow_mag": 2.0, "hsv_var": 600.0},
        seconds_since_movement=3 * 3600,
    )
    assert state == "parked"
    assert conf == 1.0
