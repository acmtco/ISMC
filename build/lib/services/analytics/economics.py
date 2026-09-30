"""КИТ, часы простоя, стоимость простоя (docs/04-metrics.md, раздел 8).

```
Потери от простоя = Σ_техника (mh_idle × стоимость_машино_часа)
Эффект            = Потери × доля_устранимых_простоев
```

Стоимость машино-часа — `data/ref/machine_hour_cost.json` (оценка, требует
уточнения — см. `_source` в файле). `доля_устранимых_простоев` — намеренно
не хранится в коде/конфиге: это допущение, которое нужно обосновать
(docs/04-metrics.md), поэтому вызывающая сторона обязана передать его явно.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CostReference:
    currency: str
    cost_per_machine_hour: dict[str, float]

    @classmethod
    def from_json(cls, path: Path) -> CostReference:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            currency=raw.get("currency", "RUB"),
            cost_per_machine_hour=raw["cost_per_machine_hour"],
        )

    def cost_of(self, cls: str, hours: float) -> float:
        rate = self.cost_per_machine_hour.get(cls)
        return rate * hours if rate is not None else 0.0


@dataclass(frozen=True)
class UtilizationSummary:
    zone_id: str
    cls: str
    mh_present: float
    mh_active: float
    mh_idle: float
    utilization: float
    idle_cost_rub: float


def utilization(mh_active: float, mh_present: float) -> float:
    """КИТ = mh_active / mh_present."""
    return mh_active / mh_present if mh_present > 0 else 0.0


def summarize_utilization(
    machine_hour_rows: list[dict], cost_ref: CostReference
) -> list[UtilizationSummary]:
    summaries = []
    for row in machine_hour_rows:
        mh_present = row["mh_present"]
        mh_active = row["mh_active"]
        mh_idle = row.get("mh_idle", mh_present - mh_active)
        summaries.append(
            UtilizationSummary(
                zone_id=row["zone_id"],
                cls=row["cls"],
                mh_present=mh_present,
                mh_active=mh_active,
                mh_idle=mh_idle,
                utilization=round(utilization(mh_active, mh_present), 2),
                idle_cost_rub=round(cost_ref.cost_of(row["cls"], mh_idle), 2),
            )
        )
    return summaries


def idle_cost_rub(mh_idle_by_class: dict[str, float], cost_ref: CostReference) -> float:
    """Потери от простоя = Σ_техника (mh_idle × стоимость_машино_часа)."""
    return sum(cost_ref.cost_of(cls, hours) for cls, hours in mh_idle_by_class.items())


def recoverable_effect_rub(total_idle_cost_rub: float, recoverable_share: float) -> float:
    """Эффект = Потери × доля_устранимых_простоев."""
    return total_idle_cost_rub * recoverable_share
