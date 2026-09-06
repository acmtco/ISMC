import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.eval.deviations_metrics import (
    _match,
    _type_metrics,
    build_schedule_dicts,
    evaluate_deviations,
)
from scripts.make_synthetic import generate
from scripts.synth.scenario import load_scenario
from services.analytics.deviations import DeviationEngine
from services.analytics.machine_hours import aggregate_machine_hours

MSK = timezone(timedelta(hours=3))


def _dev(dev_id: str, dtype: str, zone_id: str, date_from: str, date_to: str) -> dict:
    return {
        "deviation_id": dev_id,
        "type": dtype,
        "zone_id": zone_id,
        "period": {"from": date_from, "to": date_to},
    }


def test_match_same_type_zone_overlapping_period():
    detected = [_dev("D-1", "R1_resource_gap", "Z-PIT", "2026-09-18", "2026-09-20")]
    expected = [_dev("E-1", "R1_resource_gap", "Z-PIT", "2026-09-19", "2026-09-21")]
    pairs = _match(detected, expected)
    assert len(pairs) == 1


def test_match_rejects_different_zone():
    detected = [_dev("D-1", "R1_resource_gap", "Z-PIT", "2026-09-18", "2026-09-20")]
    expected = [_dev("E-1", "R1_resource_gap", "Z-FRAME", "2026-09-18", "2026-09-20")]
    assert _match(detected, expected) == []


def test_match_rejects_non_overlapping_period():
    detected = [_dev("D-1", "R1_resource_gap", "Z-PIT", "2026-09-01", "2026-09-05")]
    expected = [_dev("E-1", "R1_resource_gap", "Z-PIT", "2026-09-20", "2026-09-25")]
    assert _match(detected, expected) == []


def test_match_is_greedy_one_to_one():
    detected = [
        _dev("D-1", "R1_resource_gap", "Z-PIT", "2026-09-18", "2026-09-20"),
        _dev("D-2", "R1_resource_gap", "Z-PIT", "2026-09-19", "2026-09-21"),
    ]
    expected = [_dev("E-1", "R1_resource_gap", "Z-PIT", "2026-09-18", "2026-09-22")]
    pairs = _match(detected, expected)
    assert len(pairs) == 1  # второе совпадение не может забрать тот же expected повторно


def test_type_metrics_perfect_match():
    detected = [_dev("D-1", "R1_resource_gap", "Z-PIT", "2026-09-18", "2026-09-20")]
    expected = [_dev("E-1", "R1_resource_gap", "Z-PIT", "2026-09-18", "2026-09-20")]
    metrics, delays = _type_metrics("R1_resource_gap", detected, expected)
    assert metrics.precision == pytest.approx(1.0)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.f1 == pytest.approx(1.0)
    assert delays == [0]


def test_type_metrics_missed_expected_has_zero_recall():
    metrics, _ = _type_metrics("R1_resource_gap", [], [_dev("E-1", "R1_resource_gap", "Z-PIT", "2026-09-18", "2026-09-20")])
    assert metrics.recall == 0.0
    assert metrics.precision is None  # ничего не найдено — precision не определён


def test_type_metrics_false_positive_has_zero_precision():
    metrics, _ = _type_metrics("R1_resource_gap", [_dev("D-1", "R1_resource_gap", "Z-PIT", "2026-09-18", "2026-09-20")], [])
    assert metrics.precision == 0.0
    assert metrics.recall is None


def test_type_metrics_delay_measures_late_detection():
    detected = [_dev("D-1", "R1_resource_gap", "Z-PIT", "2026-09-20", "2026-09-22")]
    expected = [_dev("E-1", "R1_resource_gap", "Z-PIT", "2026-09-18", "2026-09-25")]
    metrics, delays = _type_metrics("R1_resource_gap", detected, expected)
    assert delays == [2]
    assert metrics.mean_delay_days == pytest.approx(2.0)


@pytest.fixture(scope="module")
def small_benchmark(tmp_path_factory):
    scenario = load_scenario(Path("data/ref/scenario_demo.yaml"))
    tmp_path = tmp_path_factory.mktemp("eval_dev")
    generate(
        scenario,
        days=scenario.days,
        sprites_dir=tmp_path / "sprites",
        out_dir=tmp_path / "frames",
        benchmark_dir=tmp_path / "bench",
    )
    return scenario, tmp_path / "bench"


def test_build_schedule_dicts_derives_planned_mh(small_benchmark):
    scenario, _ = small_benchmark
    schedule = build_schedule_dicts(scenario)
    assert len(schedule) == len(scenario.schedule)
    for entry in schedule:
        assert entry["planned_mh"]  # непустой план для каждой работы
        assert all(v > 0 for v in entry["planned_mh"].values())


def test_evaluate_deviations_recovers_injected_deviations(small_benchmark):
    scenario, bench_dir = small_benchmark
    ground_truth = [
        json.loads(line)
        for line in (bench_dir / "ground_truth.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    expected = [
        json.loads(line)
        for line in (bench_dir / "expected_deviations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    machine_hours = aggregate_machine_hours(ground_truth, object_id="OBJ-001")

    engine = DeviationEngine.load(
        work_signatures_path=Path("data/ref/work_signatures.json"),
        matching_config_path=Path("config/matching.yaml"),
        thresholds_path=Path("config/thresholds.yaml"),
        machine_hour_cost_path=Path("data/ref/machine_hour_cost.json"),
    )
    last_day = max(datetime.fromisoformat(r["ts"]).date() for r in ground_truth)
    as_of = datetime.combine(last_day, datetime.min.time(), tzinfo=MSK) + timedelta(days=1)

    result = evaluate_deviations(
        scenario=scenario,
        machine_hours=machine_hours,
        detections=ground_truth,
        expected_deviations=expected,
        engine=engine,
        as_of=as_of,
    )

    # На "идеальных" (ground truth) детекциях правила должны находить
    # внедрённые отклонения с высокой полнотой — это проверяет правила
    # Р1-Р4 и подбор planned_mh, а не качество классификатора состояния.
    assert result.overall.recall is not None
    assert result.overall.recall > 0.5
