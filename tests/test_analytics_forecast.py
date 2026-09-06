from datetime import date

import pytest

from services.analytics.forecast import (
    ForecastConfig,
    SpiThresholds,
    daily_rate,
    forecast_work,
    mh_plan_to_date,
    reverse_task,
)

CONFIG = ForecastConfig(rate_window_days=7, shift_hours=8.0)
SPI = SpiThresholds(green_min=0.95, yellow_min=0.80)


def test_mh_plan_to_date_linear_distribution():
    start, finish = date(2026, 9, 1), date(2026, 9, 10)  # 10 суток
    as_of = date(2026, 9, 5)  # 5-е сутки
    assert mh_plan_to_date(100.0, start, finish, as_of) == pytest.approx(50.0)


def test_mh_plan_to_date_clips_before_start_and_after_finish():
    start, finish = date(2026, 9, 1), date(2026, 9, 10)
    assert mh_plan_to_date(100.0, start, finish, date(2026, 8, 1)) == 0.0
    assert mh_plan_to_date(100.0, start, finish, date(2026, 10, 1)) == pytest.approx(100.0)


def test_daily_rate_averages_within_window():
    as_of = date(2026, 9, 10)
    mh_by_date = {date(2026, 9, d): 10.0 for d in range(4, 11)}  # 7 суток по 10ч
    assert daily_rate(mh_by_date, as_of, window_days=7) == pytest.approx(10.0)


def test_daily_rate_ignores_values_outside_window():
    as_of = date(2026, 9, 10)
    mh_by_date = {date(2026, 9, 1): 1000.0, date(2026, 9, 10): 10.0}
    assert daily_rate(mh_by_date, as_of, window_days=1) == pytest.approx(10.0)


def test_forecast_work_on_track_is_green():
    result = forecast_work(
        planned_mh_total=100.0,
        start_plan=date(2026, 9, 1),
        finish_plan=date(2026, 9, 10),
        mh_fact_by_date={date(2026, 9, d): 10.0 for d in range(1, 6)},
        as_of=date(2026, 9, 5),
        config=CONFIG,
        spi_thresholds=SPI,
    )
    assert result.spi == pytest.approx(1.0)
    assert result.status == "green"
    assert result.delay_days == 0


def test_forecast_work_behind_schedule_predicts_delay():
    # план 180ч за 18 суток (10ч/сут), факт — 5ч/сут первые 10 суток
    result = forecast_work(
        planned_mh_total=180.0,
        start_plan=date(2026, 9, 1),
        finish_plan=date(2026, 9, 18),
        mh_fact_by_date={date(2026, 9, d): 5.0 for d in range(1, 11)},
        as_of=date(2026, 9, 10),
        config=CONFIG,
        spi_thresholds=SPI,
    )
    assert result.status == "red"
    assert result.delay_days is not None
    assert result.delay_days > 0


def test_forecast_work_zero_rate_has_no_forecast_finish():
    result = forecast_work(
        planned_mh_total=100.0,
        start_plan=date(2026, 9, 1),
        finish_plan=date(2026, 9, 10),
        mh_fact_by_date={},
        as_of=date(2026, 9, 5),
        config=CONFIG,
        spi_thresholds=SPI,
    )
    assert result.forecast_finish is None
    assert result.delay_days is None
    assert result.status == "red"


def test_spi_status_thresholds():
    assert SPI.status(1.0) == "green"
    assert SPI.status(0.95) == "green"
    assert SPI.status(0.90) == "yellow"
    assert SPI.status(0.80) == "yellow"
    assert SPI.status(0.79) == "red"


def test_reverse_task_no_gap_needs_nothing():
    result = reverse_task(
        planned_mh_total=100.0,
        fact_to_date=50.0,
        finish_plan=date(2026, 9, 20),
        as_of=date(2026, 9, 10),
        current_rate_mh_per_day=10.0,  # требуется 50/10=5ч/сут — темп уже с запасом
        class_shares={"excavator": 1.0},
        config=CONFIG,
    )
    assert result.gap_mh_per_day == 0.0
    assert result.additional_units == {}


def test_reverse_task_computes_additional_units():
    # осталось 10 суток, нужно закрыть 100ч -> требуемый темп 10ч/сут,
    # текущий темп 2ч/сут -> дефицит 8ч/сут, при смене 8ч это 1 доп. единица
    result = reverse_task(
        planned_mh_total=150.0,
        fact_to_date=50.0,
        finish_plan=date(2026, 9, 20),
        as_of=date(2026, 9, 10),
        current_rate_mh_per_day=2.0,
        class_shares={"excavator": 1.0},
        config=CONFIG,
    )
    assert result.required_rate_mh_per_day == pytest.approx(10.0)
    assert result.gap_mh_per_day == pytest.approx(8.0)
    assert result.additional_units == {"excavator": 1}


def test_reverse_task_splits_across_classes_by_share():
    result = reverse_task(
        planned_mh_total=200.0,
        fact_to_date=0.0,
        finish_plan=date(2026, 9, 11),
        as_of=date(2026, 9, 1),
        current_rate_mh_per_day=0.0,
        class_shares={"excavator": 0.6, "dump_truck": 0.4},
        config=CONFIG,
    )
    # требуемый темп 200/10=20ч/сут; excavator 60% -> 12ч/8ч смену -> 2 ед; dump_truck 40% -> 8ч -> 1 ед
    assert result.additional_units == {"excavator": 2, "dump_truck": 1}


def test_reverse_task_returns_none_when_deadline_passed():
    result = reverse_task(
        planned_mh_total=100.0,
        fact_to_date=50.0,
        finish_plan=date(2026, 9, 1),
        as_of=date(2026, 9, 5),
        current_rate_mh_per_day=1.0,
        class_shares={"excavator": 1.0},
        config=CONFIG,
    )
    assert result is None


def test_reverse_task_returns_none_when_already_complete():
    result = reverse_task(
        planned_mh_total=100.0,
        fact_to_date=100.0,
        finish_plan=date(2026, 9, 20),
        as_of=date(2026, 9, 5),
        current_rate_mh_per_day=1.0,
        class_shares={"excavator": 1.0},
        config=CONFIG,
    )
    assert result is None
