from pathlib import Path

import pytest

from scripts.eval.state_metrics import evaluate_state_classifier
from scripts.make_synthetic import generate
from scripts.synth.scenario import load_scenario


@pytest.fixture(scope="module")
def ground_truth_path(tmp_path_factory):
    scenario = load_scenario(Path("data/ref/scenario_demo.yaml"))
    tmp_path = tmp_path_factory.mktemp("eval_state")
    generate(
        scenario,
        days=15,
        sprites_dir=tmp_path / "sprites",
        out_dir=tmp_path / "frames",
        benchmark_dir=tmp_path / "bench",
    )
    return tmp_path / "bench" / "ground_truth.jsonl"


def test_evaluate_state_classifier_returns_active_and_idle(ground_truth_path):
    result = evaluate_state_classifier(ground_truth_path)
    assert "active" in result.labels
    assert "idle" in result.labels
    assert result.n_train > 0
    assert result.n_test > 0
    assert 0.0 <= result.accuracy <= 1.0


def test_evaluate_state_classifier_confusion_matrix_shape(ground_truth_path):
    result = evaluate_state_classifier(ground_truth_path)
    n = len(result.labels)
    assert result.confusion.shape == (n, n)
    assert result.confusion.sum() == result.n_test


def test_evaluate_state_classifier_per_state_metrics_sum_to_support(ground_truth_path):
    result = evaluate_state_classifier(ground_truth_path)
    total_support = sum(m.support for m in result.by_state)
    assert total_support == result.n_test
    for m in result.by_state:
        assert 0.0 <= m.precision <= 1.0
        assert 0.0 <= m.recall <= 1.0
        assert 0.0 <= m.f1 <= 1.0


def test_evaluate_state_classifier_beats_edge_imi_on_synthetic_features(ground_truth_path):
    # те же честные, чисто разделимые синтетические признаки, что и в
    # services/perception/state.py — ожидаем высокую точность (см. P2)
    result = evaluate_state_classifier(ground_truth_path)
    assert result.accuracy > 0.9
