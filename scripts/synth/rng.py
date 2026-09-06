"""Детерминированные генераторы случайности.

`random.Random(int)` детерминирован для целых чисел независимо от
`PYTHONHASHSEED`, поэтому все составные "ключи" (день, класс, юнит, кадр)
сводятся к одному int через `combine_seed`, а не через hash() строк/кортежей.
"""
from __future__ import annotations

import random

_MULT = 1_000_003
_MASK = 0xFFFFFFFF


def combine_seed(seed: int, *parts: int) -> int:
    h = seed & _MASK
    for p in parts:
        h = (h * _MULT + (int(p) & _MASK)) & _MASK
    return h


def rng_for(seed: int, *parts: int) -> random.Random:
    return random.Random(combine_seed(seed, *parts))
