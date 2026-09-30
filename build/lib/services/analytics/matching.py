"""Ресурсный отпечаток вида работ и match_score (docs/03-deviation-rules.md, §1-2).

```
cover(w)    = Σ_c min(o_c, typical_c) / Σ_c typical_c
excess(w)   = Σ_{c∈forbidden} o_c / (Σ_c o_c + ε)
rhythm(w)   = 1 - |observed_rhythm - typical| / typical, clip[0,1]
match_score = weights.cover*cover + weights.rhythm*rhythm + weights.excess*(1-excess)
```

Веса и epsilon — `config/matching.yaml`, ни одного магического числа в коде.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ClassRange:
    min: int
    typical: float


@dataclass(frozen=True)
class RhythmSpec:
    metric: str
    min: float
    typical: float


@dataclass(frozen=True)
class WorkSignature:
    work_type: str
    required: dict[str, ClassRange]
    supporting: dict[str, ClassRange]
    forbidden: list[str]
    rhythm: RhythmSpec | None

    def expected_classes(self) -> dict[str, float]:
        """Объединённый набор классов с `typical` — и ключевых, и вспомогательных."""
        return {
            **{c: r.typical for c, r in self.required.items()},
            **{c: r.typical for c, r in self.supporting.items()},
        }


@dataclass(frozen=True)
class MatchingConfig:
    cover_weight: float
    rhythm_weight: float
    excess_weight: float
    low_confidence_threshold: float
    epsilon: float

    @classmethod
    def from_yaml(cls, path: Path) -> MatchingConfig:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            cover_weight=float(raw["weights"]["cover"]),
            rhythm_weight=float(raw["weights"]["rhythm"]),
            excess_weight=float(raw["weights"]["excess"]),
            low_confidence_threshold=float(raw["low_confidence_threshold"]),
            epsilon=float(raw["epsilon"]),
        )


def _class_range_map(raw: dict) -> dict[str, ClassRange]:
    return {
        cls: ClassRange(min=int(v["min"]), typical=float(v["typical"])) for cls, v in raw.items()
    }


def load_signatures(path: Path) -> dict[str, WorkSignature]:
    raw_list = json.loads(Path(path).read_text(encoding="utf-8"))
    signatures: dict[str, WorkSignature] = {}
    for raw in raw_list:
        rhythm_raw = raw.get("rhythm")
        rhythm = None
        if rhythm_raw:
            rhythm = RhythmSpec(
                metric=rhythm_raw["metric"],
                min=float(rhythm_raw["min"]),
                typical=float(rhythm_raw["typical"]),
            )
        signature = WorkSignature(
            work_type=raw["work_type"],
            required=_class_range_map(raw.get("required", {})),
            supporting=_class_range_map(raw.get("supporting", {})),
            forbidden=list(raw.get("forbidden", [])),
            rhythm=rhythm,
        )
        signatures[signature.work_type] = signature
    return signatures


def cover(observed: dict[str, float], signature: WorkSignature) -> float:
    expected = signature.expected_classes()
    if not expected:
        return 0.0
    numerator = sum(min(observed.get(cls, 0.0), typical) for cls, typical in expected.items())
    denominator = sum(expected.values())
    return numerator / denominator if denominator > 0 else 0.0


def excess(observed: dict[str, float], signature: WorkSignature, epsilon: float) -> float:
    total = sum(observed.values())
    forbidden_total = sum(observed.get(cls, 0.0) for cls in signature.forbidden)
    return forbidden_total / (total + epsilon)


def rhythm_score(observed_rhythm: float | None, signature: WorkSignature) -> float:
    """1.0 (нейтрально), если ритм не задан для вида работ или не измерен —
    например, для видов работ без штатного метрического ритма (facade)."""
    spec = signature.rhythm
    if spec is None or observed_rhythm is None or spec.typical == 0:
        return 1.0
    score = 1.0 - abs(observed_rhythm - spec.typical) / spec.typical
    return min(max(score, 0.0), 1.0)


def match_score(
    observed: dict[str, float],
    signature: WorkSignature,
    config: MatchingConfig,
    observed_rhythm: float | None = None,
) -> float:
    c = cover(observed, signature)
    e = excess(observed, signature, config.epsilon)
    r = rhythm_score(observed_rhythm, signature)
    return config.cover_weight * c + config.rhythm_weight * r + config.excess_weight * (1 - e)


@dataclass(frozen=True)
class MatchResult:
    work_type: str
    score: float


def best_match(
    observed: dict[str, float],
    candidate_work_types: list[str],
    signatures: dict[str, WorkSignature],
    config: MatchingConfig,
    observed_rhythm_by_type: dict[str, float] | None = None,
) -> MatchResult | None:
    """Работа с максимальным match_score среди кандидатов; None, если кандидатов нет."""
    observed_rhythm_by_type = observed_rhythm_by_type or {}
    results = [
        MatchResult(
            work_type=wt,
            score=match_score(observed, signatures[wt], config, observed_rhythm_by_type.get(wt)),
        )
        for wt in candidate_work_types
        if wt in signatures
    ]
    if not results:
        return None
    return max(results, key=lambda r: r.score)


def best_competing_match(
    observed: dict[str, float],
    exclude_work_type: str,
    signatures: dict[str, WorkSignature],
    config: MatchingConfig,
    observed_rhythm_by_type: dict[str, float] | None = None,
) -> MatchResult | None:
    """Лучший результат среди ВСЕХ известных видов работ, кроме `exclude_work_type`
    — используется правилом Р3(б): "состав техники похож на другую работу"."""
    candidates = [wt for wt in signatures if wt != exclude_work_type]
    return best_match(observed, candidates, signatures, config, observed_rhythm_by_type)
