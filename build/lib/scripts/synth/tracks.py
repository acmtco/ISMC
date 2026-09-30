"""Стабильные track_id для юнитов техники.

Присваивается по первому появлению в детерминированном порядке обхода
(день -> кадр -> зона -> класс -> unit_index), поэтому одинаковый сценарий и
код всегда дают одинаковые track_id, а один и тот же юнит держит один и тот
же track_id все сутки, пока он есть в кадре (условие reproducibility).
"""
from __future__ import annotations


class TrackRegistry:
    def __init__(self) -> None:
        self._ids: dict[tuple[str, str, int], int] = {}
        self._next = 1

    def get(self, zone_id: str, cls: str, unit_index: int) -> int:
        key = (zone_id, cls, unit_index)
        if key not in self._ids:
            self._ids[key] = self._next
            self._next += 1
        return self._ids[key]
