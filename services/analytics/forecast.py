"""Прогноз срыва срока и обратная задача (docs/03-deviation-rules.md, шаг 4).

```
mh_plan_total(w)   = Σ_c planned_mh[c]
mh_fact_total(w,t) = Σ_c mh_active накопленным итогом
rate(w,t)          = скользящее среднее mh_active за N суток (config), ч/сут
forecast_finish    = t + (mh_plan_total - mh_fact_total) / rate
delay_days         = forecast_finish - finish_plan
SPI                = mh_fact_total(t) / mh_plan_to_date(t)
```

Обратная задача — главная фича для руководителя: не "вы отстаёте на N дней",
а "чтобы уложиться в срок, нужно добавить X единиц техники с такой-то даты".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ForecastConfig:
    rate_window_days: int
    shift_hours: float

    @classmethod
    def from_yaml(cls, path: Path) -> ForecastConfig:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["forecast"]
        return cls(
            rate_window_days=int(raw["rate_window_days"]),
            shift_hours=float(raw["shift_hours"]),
        )


@dataclass(frozen=True)
class SpiThresholds:
    green_min: float
    yellow_min: float

    @classmethod
    def from_yaml(cls, path: Path) -> SpiThresholds:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["spi"]
        return cls(green_min=float(raw["green_min"]), yellow_min=float(raw["yellow_min"]))

    def status(self, spi: float) -> str:
        if spi >= self.green_min:
            return "green"
        if spi >= self.yellow_min:
            return "yellow"
        return "red"


@dataclass(frozen=True)
class ForecastResult:
    date: date
    mh_plan_to_date: float
    mh_fact_to_date: float
    spi: float
    rate_mh_per_day: float
    forecast_finish: date | None
    delay_days: int | None
    status: str


def mh_plan_to_date(
    planned_mh_total: float, start_plan: date, finish_plan: date, as_of: date
) -> float:
    """Линейное распределение планового объёма по календарным суткам работы."""
    total_days = (finish_plan - start_plan).days + 1
    if total_days <= 0:
        return planned_mh_total
    elapsed_days = min(max((as_of - start_plan).days + 1, 0), total_days)
    return planned_mh_total * elapsed_days / total_days


def daily_rate(mh_fact_by_date: dict[date, float], as_of: date, window_days: int) -> float:
    """Скользящее среднее суточных mh_active за `window_days`, ч/сут."""
    window_start = as_of - timedelta(days=window_days - 1)
    values = [mh for d, mh in mh_fact_by_date.items() if window_start <= d <= as_of]
    return sum(values) / len(values) if values else 0.0


def forecast_work(
    *,
    planned_mh_total: float,
    start_plan: date,
    finish_plan: date,
    mh_fact_by_date: dict[date, float],
    as_of: date,
    config: ForecastConfig,
    spi_thresholds: SpiThresholds,
) -> ForecastResult:
    plan_to_date = mh_plan_to_date(planned_mh_total, start_plan, finish_plan, as_of)
    fact_to_date = sum(mh for d, mh in mh_fact_by_date.items() if d <= as_of)
    spi = fact_to_date / plan_to_date if plan_to_date > 0 else 1.0

    rate = daily_rate(mh_fact_by_date, as_of, config.rate_window_days)
    remaining_mh = planned_mh_total - fact_to_date

    forecast_finish: date | None = None
    delay_days: int | None = None
    if rate > 0:
        days_needed = math.ceil(remaining_mh / rate) if remaining_mh > 0 else 0
        forecast_finish = as_of + timedelta(days=days_needed)
        delay_days = (forecast_finish - finish_plan).days

    return ForecastResult(
        date=as_of,
        mh_plan_to_date=round(plan_to_date, 2),
        mh_fact_to_date=round(fact_to_date, 2),
        spi=round(spi, 2),
        rate_mh_per_day=round(rate, 2),
        forecast_finish=forecast_finish,
        delay_days=delay_days,
        status=spi_thresholds.status(spi),
    )


@dataclass(frozen=True)
class ReverseTaskResult:
    required_rate_mh_per_day: float
    gap_mh_per_day: float
    additional_units: dict[str, int]


def reverse_task(
    *,
    planned_mh_total: float,
    fact_to_date: float,
    finish_plan: date,
    as_of: date,
    current_rate_mh_per_day: float,
    class_shares: dict[str, float],
    config: ForecastConfig,
) -> ReverseTaskResult | None:
    """"Сколько техники добавить, чтобы уложиться в срок" (docs/03, шаг 4).

    `class_shares` — доля класса в плановом объёме работы (Σ ≈ 1.0). Одна
    дополнительная единица класса даёт `config.shift_hours` маш.-ч/сутки —
    упрощение (полная смена без простоев), консервативно в пользу подрядчика.
    """
    remaining_days = (finish_plan - as_of).days
    if remaining_days <= 0:
        return None
    remaining_mh = planned_mh_total - fact_to_date
    if remaining_mh <= 0:
        return None

    required_rate = remaining_mh / remaining_days
    gap = required_rate - current_rate_mh_per_day
    if gap <= 0:
        return ReverseTaskResult(
            required_rate_mh_per_day=round(required_rate, 2),
            gap_mh_per_day=0.0,
            additional_units={},
        )

    additional_units: dict[str, int] = {}
    for cls, share in class_shares.items():
        units = math.ceil(gap * share / config.shift_hours)
        if units > 0:
            additional_units[cls] = units

    return ReverseTaskResult(
        required_rate_mh_per_day=round(required_rate, 2),
        gap_mh_per_day=round(gap, 2),
        additional_units=additional_units,
    )
