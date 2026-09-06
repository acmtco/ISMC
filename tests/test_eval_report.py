import numpy as np

from scripts.eval.deviations_metrics import DeviationEvaluation, DeviationTypeMetrics
from scripts.eval.machine_hours_metrics import MachineHoursError
from scripts.eval.performance import PerformanceEstimate
from scripts.eval.report import render_markdown, save_charts
from scripts.eval.state_metrics import ClassStateMetrics, StateEvaluation

STATE_EVAL = StateEvaluation(
    accuracy=0.95,
    by_state=[
        ClassStateMetrics(state="active", precision=0.9, recall=0.95, f1=0.92, support=100),
        ClassStateMetrics(state="idle", precision=0.93, recall=0.88, f1=0.90, support=80),
        ClassStateMetrics(state="parked", precision=1.0, recall=1.0, f1=1.0, support=20),
    ],
    confusion=np.array([[95, 5, 0], [10, 70, 0], [0, 0, 20]]),
    labels=["active", "idle", "parked"],
    n_train=800,
    n_test=200,
)

MH_ERROR = MachineHoursError(
    mae_active_hours=0.4, mape_active_pct=8.0, mae_present_hours=0.2, bias_active_hours=0.05, n_rows=90
)

DEVIATION_EVAL = DeviationEvaluation(
    by_type=[
        DeviationTypeMetrics("R1_resource_gap", 1, 1, 1, 1.0, 1.0, 1.0, 0.0),
        DeviationTypeMetrics("R2_idle", 1, 0, 0, None, 0.0, None, None),
        DeviationTypeMetrics("R3_front_mismatch", 0, 0, 0, None, None, None, None),
        DeviationTypeMetrics("R4_silence", 1, 1, 1, 1.0, 1.0, 1.0, 1.0),
    ],
    overall=DeviationTypeMetrics("Всего", 3, 2, 2, 1.0, 0.67, 1.0, 0.5),
    detected_raw=[],
)

PERFORMANCE = PerformanceEstimate(
    fps_cpu_perception_only=150.0,
    seconds_per_camera_day=1.2,
    cost_per_camera_day_rub=0.01,
    cost_per_1000_cameras_per_day_rub=10.0,
)


def test_render_markdown_without_detector_shows_placeholders():
    md = render_markdown(
        detection=None,
        tracking=None,
        state_eval=STATE_EVAL,
        mh_error=MH_ERROR,
        deviation_eval=DEVIATION_EVAL,
        performance=PERFORMANCE,
        benchmark_days=30,
        chart_paths={"state_confusion": "img/a.png", "mh_active": "img/b.png", "deviations": "img/c.png"},
    )
    assert "нет в репозитории" in md
    assert "| — | — | — | — | — | — |" in md
    assert "MOTA | — |" in md


def test_render_markdown_includes_computed_numbers():
    md = render_markdown(
        detection=None,
        tracking=None,
        state_eval=STATE_EVAL,
        mh_error=MH_ERROR,
        deviation_eval=DEVIATION_EVAL,
        performance=PERFORMANCE,
        benchmark_days=30,
        chart_paths={"state_confusion": "img/a.png", "mh_active": "img/b.png", "deviations": "img/c.png"},
    )
    assert "0.40" in md  # MAE mh_active
    assert "R1_resource_gap" in md
    assert "R2_idle" in md
    assert "150.0" in md  # fps


def test_render_markdown_never_writes_none_literal():
    """Регрессия: `None` не должен просачиваться в markdown как текст —
    только "—" (см. `_fmt`)."""
    md = render_markdown(
        detection=None,
        tracking=None,
        state_eval=STATE_EVAL,
        mh_error=MH_ERROR,
        deviation_eval=DEVIATION_EVAL,
        performance=PERFORMANCE,
        benchmark_days=30,
        chart_paths={"state_confusion": "img/a.png", "mh_active": "img/b.png", "deviations": "img/c.png"},
    )
    assert "None" not in md


def test_save_charts_creates_png_files(tmp_path):
    paths = save_charts(
        tmp_path,
        state_eval=STATE_EVAL,
        predicted_rows=[{"date": "2026-09-01", "mh_active": 5.0}],
        truth_rows=[{"date": "2026-09-01", "mh_active": 6.0}],
        deviation_eval=DEVIATION_EVAL,
    )
    assert (tmp_path / "state_confusion_matrix.png").exists()
    assert (tmp_path / "mh_active_predicted_vs_truth.png").exists()
    assert (tmp_path / "deviation_precision_recall.png").exists()
    assert paths["state_confusion"] == "img/state_confusion_matrix.png"
