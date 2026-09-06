"""Один фикстурный кейс на каждое правило Р0-Р4 (docs/03-deviation-rules.md)."""
from datetime import date, datetime, timedelta, timezone

from services.analytics.deviations import DeviationEngine, Thresholds
from services.analytics.economics import CostReference
from services.analytics.forecast import ForecastConfig, SpiThresholds
from services.analytics.machine_hours import DayQuality
from services.analytics.matching import ClassRange, MatchingConfig, RhythmSpec, WorkSignature

MSK = timezone(timedelta(hours=3))
AS_OF = datetime(2026, 9, 25, 19, 5, tzinfo=MSK)

EXCAVATION = WorkSignature(
    work_type="earthworks_excavation",
    required={"excavator": ClassRange(min=1, typical=2)},
    supporting={"dump_truck": ClassRange(min=2, typical=5), "bulldozer": ClassRange(min=0, typical=1)},
    forbidden=["tower_crane"],
    rhythm=RhythmSpec(metric="dump_truck_cycles_per_shift", min=6, typical=12),
)

FRAME = WorkSignature(
    work_type="frame_assembly",
    required={"tower_crane": ClassRange(min=1, typical=1)},
    supporting={"mobile_crane": ClassRange(min=0, typical=1)},
    forbidden=["excavator", "bulldozer"],
    rhythm=None,
)

THRESHOLDS = Thresholds(
    r1_fact_vs_plan_ratio=0.7,
    r1_min_consecutive_days=2,
    r1_min_coverage=0.6,
    r1_high_severity_delay_days=3,
    r2_utilization_max=0.5,
    r2_min_mh_present_per_shift=4.0,
    r2_high_severity_period_cost_rub=50000,
    r3_low_match_score=0.35,
    r3_competing_match_score=0.6,
    r3_high_severity_min_days=3,
    r4_min_consecutive_days=2,
    r4_min_coverage=0.8,
    r0_min_coverage=0.6,
    r0_min_quality_score=0.5,
)
MATCHING_CONFIG = MatchingConfig(
    cover_weight=0.55, rhythm_weight=0.25, excess_weight=0.20, low_confidence_threshold=0.35, epsilon=1e-6
)
FORECAST_CONFIG = ForecastConfig(rate_window_days=7, shift_hours=8.0)
SPI_THRESHOLDS = SpiThresholds(green_min=0.95, yellow_min=0.80)
COST_REF = CostReference(currency="RUB", cost_per_machine_hour={"excavator": 2500, "dump_truck": 1800})


def _engine(signatures: dict[str, WorkSignature]) -> DeviationEngine:
    return DeviationEngine(
        signatures=signatures,
        matching_config=MATCHING_CONFIG,
        thresholds=THRESHOLDS,
        forecast_config=FORECAST_CONFIG,
        spi_thresholds=SPI_THRESHOLDS,
        cost_ref=COST_REF,
    )


def _mh_row(d: date, zone_id: str, cls: str, *, present: float, active: float, units: int = 1) -> dict:
    idle = present - active
    return {
        "date": d.isoformat(),
        "object_id": "OBJ-001",
        "zone_id": zone_id,
        "cls": cls,
        "units_seen": units,
        "mh_present": present,
        "mh_active": active,
        "mh_idle": idle,
        "utilization": round(active / present, 3) if present > 0 else 0.0,
        "coverage": 1.0,
        "confidence": 0.95,
    }


def _daily_quality(days: list[date], *, coverage: float = 1.0, avg_score: float = 0.95) -> dict:
    return {d: DayQuality(coverage=coverage, avg_quality_score=avg_score, confidence=coverage * avg_score) for d in days}


def _schedule_entry(
    work_id: str,
    zone_id: str,
    work_type: str,
    start: date,
    finish: date,
    planned_mh: dict[str, float],
) -> dict:
    return {
        "work_id": work_id,
        "name": "Разработка котлована" if work_type == "earthworks_excavation" else "Монтаж каркаса",
        "work_type": work_type,
        "zone_id": zone_id,
        "start_plan": start.isoformat(),
        "finish_plan": finish.isoformat(),
        "planned_mh": planned_mh,
    }


def _dates(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


# ---------------------------------------------------------------------------
# R1 — ресурсный дефицит
# ---------------------------------------------------------------------------


def test_r1_resource_gap_triggers_on_sustained_deficit():
    zone_id = "Z-R1"
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    schedule = [_schedule_entry("W-R1", zone_id, "earthworks_excavation", start, finish, {"excavator": 20.0})]

    days = _dates(start, 6)  # 6 суток дефицита подряд, план 2ч/сут, факт 0.2ч/сут
    machine_hours = [_mh_row(d, zone_id, "excavator", present=0.3, active=0.2) for d in days]
    daily_quality = _daily_quality(days)

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=schedule, machine_hours=machine_hours, daily_quality=daily_quality, as_of=AS_OF)

    assert len(result) == 1
    dev = result[0]
    assert dev["type"] == "R1_resource_gap"
    assert dev["zone_id"] == zone_id
    assert dev["work_id"] == "W-R1"
    assert dev["period"] == {"from": "2026-09-01", "to": "2026-09-06"}
    assert dev["observed"]["excavator"] == 1
    assert dev["severity"] == "high"  # огромное отставание -> большой delay_days
    assert dev["impact"]["spi"] < 0.95
    assert "экскаватор" in dev["explanation"]


def test_r1_does_not_trigger_on_single_isolated_day():
    zone_id = "Z-R1B"
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    schedule = [_schedule_entry("W-R1B", zone_id, "earthworks_excavation", start, finish, {"excavator": 20.0})]

    days = _dates(start, 3)
    # только средний день дефицитный, до и после — план выполняется
    machine_hours = [
        _mh_row(days[0], zone_id, "excavator", present=2.0, active=2.0),
        _mh_row(days[1], zone_id, "excavator", present=0.3, active=0.2),
        _mh_row(days[2], zone_id, "excavator", present=2.0, active=2.0),
    ]
    daily_quality = _daily_quality(days)

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=schedule, machine_hours=machine_hours, daily_quality=daily_quality, as_of=AS_OF)

    assert result == []  # min_consecutive_days=2 — один день не формирует отклонение


# ---------------------------------------------------------------------------
# R2 — простой
# ---------------------------------------------------------------------------


def test_r2_idle_triggers_and_computes_cost():
    zone_id = "Z-R2"
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    # excavator присутствует по плану (2ч/сут), но простаивает: план по R1 выполнен
    schedule = [_schedule_entry("W-R2", zone_id, "earthworks_excavation", start, finish, {"excavator": 20.0})]

    day = date(2026, 9, 5)
    machine_hours = [_mh_row(day, zone_id, "excavator", present=8.0, active=2.0)]  # КИТ=0.25
    daily_quality = _daily_quality([day])

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=schedule, machine_hours=machine_hours, daily_quality=daily_quality, as_of=AS_OF)

    assert len(result) == 1
    dev = result[0]
    assert dev["type"] == "R2_idle"
    assert dev["period"] == {"from": "2026-09-05", "to": "2026-09-05"}
    assert dev["observed"]["excavator"] == 6.0  # mh_idle = 8.0 - 2.0
    assert dev["impact"]["idle_cost_rub"] == 6.0 * 2500
    assert dev["severity"] == "medium"  # ниже порога high_severity_period_cost_rub


def test_r2_high_severity_when_cost_exceeds_threshold():
    zone_id = "Z-R2H"
    start, finish = date(2026, 9, 1), date(2026, 9, 30)
    schedule = [_schedule_entry("W-R2H", zone_id, "earthworks_excavation", start, finish, {"excavator": 60.0})]

    day = date(2026, 9, 5)
    # 30 idle ч * 2500 руб = 75000 > порога 50000
    machine_hours = [_mh_row(day, zone_id, "excavator", present=32.0, active=2.0)]
    daily_quality = _daily_quality([day])

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=schedule, machine_hours=machine_hours, daily_quality=daily_quality, as_of=AS_OF)

    assert result[0]["severity"] == "high"


# ---------------------------------------------------------------------------
# R3 — несоответствие фронта
# ---------------------------------------------------------------------------


def test_r3_forbidden_equipment_present():
    zone_id = "Z-R3A"
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    # план выполняется исправно excavator'ом, но в зоне также стоит башенный кран (forbidden)
    schedule = [_schedule_entry("W-R3A", zone_id, "earthworks_excavation", start, finish, {"excavator": 20.0})]

    day = date(2026, 9, 5)
    machine_hours = [
        _mh_row(day, zone_id, "excavator", present=2.0, active=2.0),
        _mh_row(day, zone_id, "tower_crane", present=3.0, active=3.0),
    ]
    daily_quality = _daily_quality([day])

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=schedule, machine_hours=machine_hours, daily_quality=daily_quality, as_of=AS_OF)

    assert len(result) == 1
    dev = result[0]
    assert dev["type"] == "R3_front_mismatch"
    assert dev["severity"] == "medium"
    assert "башенн" in dev["explanation"].lower() or "кран" in dev["explanation"].lower()


def test_r3_competing_work_type_match():
    zone_id = "Z-R3B"
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    # график говорит "земляные работы", но по факту наблюдается состав кранового монтажа
    schedule = [_schedule_entry("W-R3B", zone_id, "earthworks_excavation", start, finish, {})]

    day = date(2026, 9, 5)
    machine_hours = [
        _mh_row(day, zone_id, "tower_crane", present=2.0, active=2.0),
        _mh_row(day, zone_id, "mobile_crane", present=1.0, active=1.0),
    ]
    daily_quality = _daily_quality([day])

    engine = _engine({"earthworks_excavation": EXCAVATION, "frame_assembly": FRAME})
    result = engine.run(schedule=schedule, machine_hours=machine_hours, daily_quality=daily_quality, as_of=AS_OF)

    assert len(result) == 1
    assert result[0]["type"] == "R3_front_mismatch"


def test_r3_activity_in_unscheduled_zone():
    zone_id = "Z-R3C"
    day = date(2026, 9, 5)
    machine_hours = [_mh_row(day, zone_id, "excavator", present=2.0, active=2.0)]
    daily_quality = _daily_quality([day])

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=[], machine_hours=machine_hours, daily_quality=daily_quality, as_of=AS_OF)

    assert len(result) == 1
    dev = result[0]
    assert dev["type"] == "R3_front_mismatch"
    assert dev["work_id"] is None
    assert dev["severity"] == "medium"  # < r3_high_severity_min_days=3


def test_r3_unscheduled_activity_escalates_to_high_after_three_days():
    zone_id = "Z-R3C-LONG"
    days = _dates(date(2026, 9, 1), 3)
    machine_hours = [_mh_row(d, zone_id, "excavator", present=2.0, active=2.0) for d in days]
    daily_quality = _daily_quality(days)

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=[], machine_hours=machine_hours, daily_quality=daily_quality, as_of=AS_OF)

    assert len(result) == 1
    assert result[0]["severity"] == "high"


# ---------------------------------------------------------------------------
# R4 — тишина
# ---------------------------------------------------------------------------


def test_r4_silence_triggers_when_scheduled_work_has_no_equipment():
    zone_id = "Z-R4"
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    schedule = [_schedule_entry("W-R4", zone_id, "earthworks_excavation", start, finish, {"excavator": 20.0})]

    days = _dates(date(2026, 9, 3), 2)  # 2 суток без единой строки machine_hours
    daily_quality = _daily_quality(days, coverage=0.9, avg_score=0.9)

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=schedule, machine_hours=[], daily_quality=daily_quality, as_of=AS_OF)

    assert len(result) == 1
    dev = result[0]
    assert dev["type"] == "R4_silence"
    assert dev["period"] == {"from": "2026-09-03", "to": "2026-09-04"}
    assert dev["severity"] == "high"
    assert dev["expected"]["excavator"] == 2  # typical по сигнатуре


def test_r4_does_not_trigger_when_coverage_too_low():
    """При низком coverage должен сработать Р0, а не Р4 (докстринг Р4)."""
    zone_id = "Z-R4-LOWCOV"
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    schedule = [_schedule_entry("W-R4L", zone_id, "earthworks_excavation", start, finish, {"excavator": 20.0})]

    days = _dates(date(2026, 9, 3), 2)
    daily_quality = _daily_quality(days, coverage=0.5, avg_score=0.9)  # < r0_min_coverage=0.6

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=schedule, machine_hours=[], daily_quality=daily_quality, as_of=AS_OF)

    assert len(result) == 1
    assert result[0]["type"] == "R0_low_confidence"


# ---------------------------------------------------------------------------
# R0 — низкое доверие
# ---------------------------------------------------------------------------


def test_r0_low_confidence_on_poor_coverage():
    # зона должна быть хоть чем-то "видна" движку (здесь — графиком), иначе
    # для неё в принципе нечего формировать: без ссылки на зону ни в графике,
    # ни в machine_hours система о ней не знает.
    zone_id = "Z-R0"
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    schedule = [_schedule_entry("W-R0", zone_id, "earthworks_excavation", start, finish, {"excavator": 20.0})]
    day = date(2026, 9, 1)
    daily_quality = {day: DayQuality(coverage=0.3, avg_quality_score=0.9, confidence=0.27)}

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=schedule, machine_hours=[], daily_quality=daily_quality, as_of=AS_OF)

    assert len(result) == 1
    dev = result[0]
    assert dev["type"] == "R0_low_confidence"
    assert dev["severity"] == "low"
    assert dev["work_id"] == "W-R0"  # R0 не "прячет" работу — просто не судит по ней


def test_r0_low_confidence_on_poor_average_quality_score():
    zone_id = "Z-R0B"
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    schedule = [_schedule_entry("W-R0B", zone_id, "earthworks_excavation", start, finish, {"excavator": 20.0})]
    day = date(2026, 9, 1)
    daily_quality = {day: DayQuality(coverage=0.9, avg_quality_score=0.2, confidence=0.18)}

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=schedule, machine_hours=[], daily_quality=daily_quality, as_of=AS_OF)

    assert len(result) == 1
    assert result[0]["type"] == "R0_low_confidence"


def test_no_deviation_when_everything_nominal():
    zone_id = "Z-OK"
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    schedule = [_schedule_entry("W-OK", zone_id, "earthworks_excavation", start, finish, {"excavator": 20.0})]
    day = date(2026, 9, 5)
    machine_hours = [_mh_row(day, zone_id, "excavator", present=2.0, active=2.0)]
    daily_quality = _daily_quality([day])

    engine = _engine({"earthworks_excavation": EXCAVATION})
    result = engine.run(schedule=schedule, machine_hours=machine_hours, daily_quality=daily_quality, as_of=AS_OF)

    assert result == []


def test_deviation_engine_loads_from_real_config_and_ref_data():
    from pathlib import Path

    engine = DeviationEngine.load(
        work_signatures_path=Path("data/ref/work_signatures.json"),
        matching_config_path=Path("config/matching.yaml"),
        thresholds_path=Path("config/thresholds.yaml"),
        machine_hour_cost_path=Path("data/ref/machine_hour_cost.json"),
    )
    assert "earthworks_excavation" in engine.signatures
    assert engine.thresholds.r1_min_consecutive_days == 2
