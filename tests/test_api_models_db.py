"""Регрессия: `MachineHourRecord(**row)` с ключом `cls` из
`machine_hours.aggregate_machine_hours()` падал с
`TypeError: SQLModel.__new__() got multiple values for argument 'cls'`,
потому что `cls` — зарезервированное имя первого параметра `__new__`.
`equipment_class` + `from_row()` — фикс, см. services/api/models_db.py.
"""
import pytest

from services.api.models_db import MachineHourRecord

SAMPLE_ROW = {
    "date": "2026-09-20",
    "object_id": "OBJ-001",
    "zone_id": "Z-PIT",
    "cls": "excavator",
    "units_seen": 2,
    "mh_present": 16.0,
    "mh_active": 11.4,
    "mh_idle": 4.6,
    "utilization": 0.71,
    "coverage": 0.93,
    "confidence": 0.88,
}


def test_from_row_maps_contract_cls_key_to_equipment_class():
    record = MachineHourRecord.from_row(SAMPLE_ROW)
    assert record.equipment_class == "excavator"
    assert record.zone_id == "Z-PIT"
    assert record.mh_active == 11.4


def test_direct_construction_with_cls_kwarg_would_have_crashed():
    """Документирует САМУ причину бага: `cls=...` как kwarg в SQLModel."""
    with pytest.raises(TypeError, match="cls"):
        MachineHourRecord(
            date="2026-09-20",
            object_id="OBJ-001",
            zone_id="Z-PIT",
            cls="excavator",
            units_seen=1,
            mh_present=1.0,
            mh_active=1.0,
            mh_idle=0.0,
            utilization=1.0,
            coverage=1.0,
            confidence=1.0,
        )
