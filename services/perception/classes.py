"""Канонический перечень классов техники — docs/02-data-contract.md, раздел 3.

Единственный источник истины для детектора: порядок здесь задаёт индексы
классов в YOLO-разметке (`scripts/train_detector.py`) и в весах модели,
поэтому менять его задним числом нельзя — обученные веса станут читаться
неправильно. Новые классы добавляются только В КОНЕЦ списка.

Соотношение с `scripts/synth/classes.py`: там свой, более узкий список для
процедурной отрисовки спрайтов, и свой порядок, завязанный на
детерминированные seed-ы синтетики. Это сознательно разные перечни —
синтетика умеет рисовать не всё, что умеет распознавать детектор.
"""
from __future__ import annotations

# Первые восемь — классы, прямо перечисленные в ТЗ (раздел 6.2).
DETECTION_CLASSES: list[str] = [
    "excavator",
    "dump_truck",
    "roller",
    "knuckle_boom_crane",
    "concrete_mixer",
    "bulldozer",
    "truck",
    "mobile_crane",
    # Расширение перечня (ТЗ это разрешает) — нужно ресурсным отпечаткам
    # работ из справочника ДГП.
    "tower_crane",
    "drilling_rig",
    "concrete_pump",
    "loader",
]

CLASS_INDEX: dict[str, int] = {name: i for i, name in enumerate(DETECTION_CLASSES)}

# Классы из ТЗ, раздел 6.2 — по ним отчитываемся отдельно в метриках.
TZ_CLASSES: list[str] = DETECTION_CLASSES[:8]
