from pathlib import Path
from textwrap import dedent

import openpyxl
import pytest

from services.analytics.schedule_io import (
    ProductivityRef,
    classify_work_type,
    derive_planned_mh,
    import_msp_xml,
    import_xlsx,
    match_columns,
    match_resource_columns,
)


def test_match_columns_recognizes_exact_headers():
    headers = ["Наименование работ", "Начало", "Окончание", "Объем", "Ед.изм", "Зона"]
    from services.analytics.schedule_io import FIELD_SYNONYMS

    columns = match_columns(headers, FIELD_SYNONYMS)
    assert columns["name"] == 0
    assert columns["start"] == 1
    assert columns["finish"] == 2
    assert columns["volume_qty"] == 3
    assert columns["volume_unit"] == 4
    assert columns["zone"] == 5


def test_match_columns_fuzzy_typo_tolerance():
    from services.analytics.schedule_io import FIELD_SYNONYMS

    headers = ["Наименование  работы", "Дата начала", "Дата окончания"]
    columns = match_columns(headers, FIELD_SYNONYMS)
    assert columns["name"] == 0
    assert columns["start"] == 1
    assert columns["finish"] == 2


def test_match_columns_does_not_assign_same_header_twice():
    from services.analytics.schedule_io import FIELD_SYNONYMS

    headers = ["Начало"]
    columns = match_columns(headers, FIELD_SYNONYMS)
    assert len(columns) == 1


def test_match_resource_columns_finds_class_by_ru_synonym():
    headers = ["Наименование", "Экскаватор, маш-ч", "Самосвал"]
    resources = match_resource_columns(headers)
    assert resources == {"excavator": 1, "dump_truck": 2}


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Разработка котлована", "earthworks_excavation"),
        ("Устройство свайного поля", "piling"),
        ("Устройство фундаментной плиты", "foundation_slab"),
        ("Монтаж каркаса здания", "frame_assembly"),
        ("Обратная засыпка пазух", "backfill"),
        ("Фасадные работы", "facade"),
        ("Прокладка инженерных сетей", "utilities"),
        ("Что-то совсем другое", None),
    ],
)
def test_classify_work_type_by_keywords(name, expected):
    assert classify_work_type(name) == expected


def test_derive_planned_mh_matches_unit_and_computes_hours():
    productivity = ProductivityRef.from_json(Path("data/ref/productivity.json"))
    planned = derive_planned_mh(
        {"unit": "м3", "qty": 12000}, "earthworks_excavation", productivity
    )
    assert planned["excavator"] == pytest.approx(12000 / 66.0, abs=0.01)
    assert planned["dump_truck"] == pytest.approx(12000 / 28.0, abs=0.01)


def test_derive_planned_mh_returns_none_on_unit_mismatch():
    productivity = ProductivityRef.from_json(Path("data/ref/productivity.json"))
    planned = derive_planned_mh({"unit": "т", "qty": 100}, "earthworks_excavation", productivity)
    assert planned is None


def test_derive_planned_mh_returns_none_for_unrecognized_work_type():
    productivity = ProductivityRef.from_json(Path("data/ref/productivity.json"))
    assert derive_planned_mh({"unit": "м3", "qty": 100}, None, productivity) is None


def _write_xlsx(path: Path, headers: list[str], rows: list[list]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_import_xlsx_parses_rows_and_derives_planned_mh(tmp_path):
    path = tmp_path / "schedule.xlsx"
    _write_xlsx(
        path,
        ["Наименование работ", "Начало", "Окончание", "Объем", "Ед.изм", "Зона", "Предшественники"],
        [
            ["Разработка котлована", "2026-09-15", "2026-10-02", 12000, "м3", "Z-PIT", ""],
            ["Монтаж каркаса", "2026-10-03", "2026-10-20", 500, "т", "Z-FRAME", "1"],
        ],
    )
    productivity = ProductivityRef.from_json(Path("data/ref/productivity.json"))
    entries = import_xlsx(path, productivity=productivity)

    assert len(entries) == 2
    first = entries[0]
    assert first["work_id"] == "W-001"
    assert first["name"] == "Разработка котлована"
    assert first["work_type"] == "earthworks_excavation"
    assert first["zone_id"] == "Z-PIT"
    assert first["start_plan"] == "2026-09-15"
    assert first["finish_plan"] == "2026-10-02"
    assert first["planned_mh"]["excavator"] == pytest.approx(12000 / 66.0, abs=0.01)

    second = entries[1]
    assert second["predecessors"] == ["W-001"]


def test_import_xlsx_imports_explicit_resource_columns(tmp_path):
    path = tmp_path / "schedule.xlsx"
    _write_xlsx(
        path,
        ["Наименование работ", "Начало", "Окончание", "Экскаватор, маш-ч", "Самосвал, маш-ч"],
        [["Разработка котлована", "2026-09-15", "2026-10-02", 180, 420]],
    )
    entries = import_xlsx(path)
    assert entries[0]["planned_mh"] == {"excavator": 180.0, "dump_truck": 420.0}


def test_import_xlsx_zone_map_translates_labels(tmp_path):
    path = tmp_path / "schedule.xlsx"
    _write_xlsx(
        path,
        ["Наименование работ", "Начало", "Окончание", "Зона"],
        [["Разработка котлована", "2026-09-15", "2026-10-02", "Котлован"]],
    )
    entries = import_xlsx(path, zone_map={"Котлован": "Z-PIT"})
    assert entries[0]["zone_id"] == "Z-PIT"


def test_import_xlsx_missing_required_columns_raises(tmp_path):
    path = tmp_path / "schedule.xlsx"
    _write_xlsx(path, ["Что-то", "Другое"], [["a", "b"]])
    with pytest.raises(ValueError, match="обязательные колонки"):
        import_xlsx(path)


MSPDI_XML = dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <Project xmlns="http://schemas.microsoft.com/project">
      <ExtendedAttributes>
        <ExtendedAttribute><FieldID>205000000</FieldID><Alias>Зона</Alias></ExtendedAttribute>
        <ExtendedAttribute><FieldID>205000001</FieldID><Alias>Объем</Alias></ExtendedAttribute>
        <ExtendedAttribute><FieldID>205000002</FieldID><Alias>Ед.изм</Alias></ExtendedAttribute>
      </ExtendedAttributes>
      <Tasks>
        <Task>
          <UID>1</UID>
          <Name>Разработка котлована</Name>
          <Start>2026-09-15T08:00:00</Start>
          <Finish>2026-10-02T17:00:00</Finish>
          <ExtendedAttribute><FieldID>205000000</FieldID><Value>Z-PIT</Value></ExtendedAttribute>
          <ExtendedAttribute><FieldID>205000001</FieldID><Value>12000</Value></ExtendedAttribute>
          <ExtendedAttribute><FieldID>205000002</FieldID><Value>м3</Value></ExtendedAttribute>
        </Task>
        <Task>
          <UID>2</UID>
          <Name>Монтаж каркаса</Name>
          <Start>2026-10-03T08:00:00</Start>
          <Finish>2026-10-20T17:00:00</Finish>
          <PredecessorLink><PredecessorUID>1</PredecessorUID></PredecessorLink>
        </Task>
      </Tasks>
    </Project>
    """
)


def test_import_msp_xml_parses_tasks_and_extended_attributes(tmp_path):
    path = tmp_path / "schedule.xml"
    path.write_text(MSPDI_XML, encoding="utf-8")
    productivity = ProductivityRef.from_json(Path("data/ref/productivity.json"))

    entries = import_msp_xml(path, productivity=productivity)

    assert len(entries) == 2
    first = entries[0]
    assert first["work_id"] == "W-001"
    assert first["name"] == "Разработка котлована"
    assert first["work_type"] == "earthworks_excavation"
    assert first["zone_id"] == "Z-PIT"
    assert first["start_plan"] == "2026-09-15"
    assert first["finish_plan"] == "2026-10-02"
    assert first["planned_mh"]["excavator"] == pytest.approx(12000 / 66.0, abs=0.01)

    second = entries[1]
    assert second["predecessors"] == ["W-001"]
