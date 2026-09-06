"""Сетка времени съёмки на сутки: дневные кадры + редкие ночные."""
from __future__ import annotations

from scripts.synth.scenario import Scenario


def night_hours(scenario: Scenario) -> list[int]:
    early = max(0, scenario.day_start_hour - 3)
    late = min(23, scenario.day_end_hour + 3)
    seen: list[int] = []
    for h in (early, late):
        if h not in seen:
            seen.append(h)
    return seen[: scenario.night_frames_per_night]


def frame_times(scenario: Scenario) -> list[tuple[int, int]]:
    times: list[tuple[int, int]] = []
    total_min = scenario.day_start_hour * 60
    end_min = scenario.day_end_hour * 60
    while total_min < end_min:
        times.append((total_min // 60, total_min % 60))
        total_min += scenario.capture_interval_min

    for h in night_hours(scenario):
        times.append((h, 0))

    times.sort()
    return times
