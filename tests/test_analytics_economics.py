from pathlib import Path

import pytest

from services.analytics.economics import (
    CostReference,
    idle_cost_rub,
    recoverable_effect_rub,
    summarize_utilization,
    utilization,
)

COST_REF = CostReference(currency="RUB", cost_per_machine_hour={"excavator": 2500, "dump_truck": 1800})


def test_utilization_ratio():
    assert utilization(mh_active=7.0, mh_present=10.0) == pytest.approx(0.7)


def test_utilization_zero_present_is_zero_not_error():
    assert utilization(mh_active=0.0, mh_present=0.0) == 0.0


def test_cost_of_known_class():
    assert COST_REF.cost_of("excavator", 4.0) == 10000


def test_cost_of_unknown_class_is_zero():
    assert COST_REF.cost_of("drilling_rig", 4.0) == 0.0


def test_idle_cost_rub_sums_across_classes():
    cost = idle_cost_rub({"excavator": 2.0, "dump_truck": 3.0}, COST_REF)
    assert cost == pytest.approx(2 * 2500 + 3 * 1800)


def test_recoverable_effect_scales_by_share():
    assert recoverable_effect_rub(10000.0, 0.4) == pytest.approx(4000.0)


def test_summarize_utilization_computes_idle_cost_per_row():
    rows = [
        {"zone_id": "Z-PIT", "cls": "excavator", "mh_present": 10.0, "mh_active": 4.0, "mh_idle": 6.0},
    ]
    [summary] = summarize_utilization(rows, COST_REF)
    assert summary.zone_id == "Z-PIT"
    assert summary.utilization == pytest.approx(0.4)
    assert summary.idle_cost_rub == pytest.approx(6.0 * 2500)


def test_cost_reference_loads_from_ref_data():
    ref = CostReference.from_json(Path("data/ref/machine_hour_cost.json"))
    assert ref.currency == "RUB"
    assert ref.cost_per_machine_hour["excavator"] > 0
