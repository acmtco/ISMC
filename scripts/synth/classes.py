"""Классы техники — см. docs/02-data-contract.md, раздел 3.

Порядок фиксирован: он участвует в детерминированных seed-ах (индекс класса).
`worker` сознательно исключён — см. CLAUDE.md, "Чего НЕ делаем": людей не
распознаём.
"""
from __future__ import annotations

CLASSES: list[str] = [
    "excavator",
    "dump_truck",
    "concrete_mixer",
    "concrete_pump",
    "tower_crane",
    "mobile_crane",
    "bulldozer",
    "roller",
    "loader",
    "drilling_rig",
]

CLASS_INDEX: dict[str, int] = {cls: i for i, cls in enumerate(CLASSES)}

# Базовый цвет корпуса для процедурной отрисовки спрайта, RGB.
CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "excavator": (214, 158, 46),
    "dump_truck": (191, 64, 44),
    "concrete_mixer": (66, 133, 191),
    "concrete_pump": (140, 96, 191),
    "tower_crane": (210, 210, 60),
    "mobile_crane": (230, 150, 40),
    "bulldozer": (120, 140, 70),
    "roller": (90, 90, 100),
    "loader": (60, 150, 140),
    "drilling_rig": (150, 70, 70),
}

# Размер спрайта (ширина, высота) в пикселях при масштабе 1.0.
CLASS_SIZE: dict[str, tuple[int, int]] = {
    "excavator": (70, 45),
    "dump_truck": (75, 40),
    "concrete_mixer": (60, 45),
    "concrete_pump": (80, 40),
    "tower_crane": (40, 140),
    "mobile_crane": (85, 55),
    "bulldozer": (65, 38),
    "roller": (55, 35),
    "loader": (55, 40),
    "drilling_rig": (40, 90),
}


def class_index(cls: str) -> int:
    return CLASS_INDEX[cls]
