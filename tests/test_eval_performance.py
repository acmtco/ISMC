import pytest

from scripts.eval.performance import estimate_performance


def test_estimate_performance_basic_formula():
    result = estimate_performance(fps=100.0, frames_per_camera_day=3600, cpu_hour_cost_rub=10.0)
    assert result.fps_cpu_perception_only == 100.0
    assert result.seconds_per_camera_day == pytest.approx(36.0)
    assert result.cost_per_camera_day_rub == pytest.approx(36.0 / 3600 * 10.0)
    assert result.cost_per_1000_cameras_per_day_rub == pytest.approx(result.cost_per_camera_day_rub * 1000)


def test_estimate_performance_zero_fps_does_not_crash():
    result = estimate_performance(fps=0.0, frames_per_camera_day=100)
    assert result.seconds_per_camera_day == 0.0
    assert result.cost_per_camera_day_rub == 0.0
