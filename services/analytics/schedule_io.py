"""Импорт графика (XLSX / MS Project XML) в `schedule.json` (docs/02, раздел 2).

Автоопределение колонок — нечёткое сопоставление заголовков листа/подписей
пользовательских полей MSPDI с известными синонимами (`FIELD_SYNONYMS`), плюс
отдельное распознавание колонок-классов техники (`ru_text.CLASS_RU_SYNONYMS`)
для прямого импорта `planned_mh`, если график его уже содержит.

Если `planned_mh` в источнике нет — выводим его из объёма работ и норм
`data/ref/productivity.json`: `planned_mh[c] = qty / productivity_per_mh[c]`
(docs/02 §2). Для этого имя работы классифицируется в `work_type` по
ключевым словам (`WORK_TYPE_KEYWORDS`) — эвристика, не ML: прозрачна и легко
правится руками, если ошиблась на конкретном графике.

Ограничения (осознанно, чтобы не тонуть в бесконечных форматах Excel):
один лист (первый или указанный по имени), первая строка — заголовки;
предшественники разбираются как ссылки на номер строки/UID с отброшенными
модификаторами лага (`12FS+2d` -> предшественник №12).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree as ET

import openpyxl

from services.analytics.ru_text import CLASS_RU_SYNONYMS

FIELD_SYNONYMS: dict[str, list[str]] = {
    "name": [
        "наименование работ",
        "наименование",
        "название",
        "работа",
        "содержание работ",
        "name",
    ],
    "start": ["начало", "дата начала", "start", "start date"],
    "finish": ["окончание", "дата окончания", "конец", "finish", "finish date"],
    "volume_qty": ["объем", "объём", "объем работ", "количество", "кол-во", "qty", "volume"],
    "volume_unit": ["ед.изм", "единица измерения", "ед. изм.", "unit"],
    "zone": ["зона", "захватка", "участок", "zone"],
    "work_type": ["вид работ", "тип работ", "категория работ", "work type"],
    "predecessors": ["предшественники", "предшествующие работы", "связи", "predecessors"],
}

COLUMN_MATCH_THRESHOLD = 0.6

WORK_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("earthworks_excavation", ["котлован", "выемк", "разработка грунт", "земляны"]),
    ("piling", ["сва", "буров"]),
    ("foundation_slab", ["фундамент", "плита"]),
    ("frame_assembly", ["каркас", "монтаж конструкц", "монтаж колонн", "монтаж плит перекрыт"]),
    ("backfill", ["засыпк"]),
    ("facade", ["фасад"]),
    ("utilities", ["сети", "коммуникац", "инженерн"]),
]

DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"]


def _normalize(text: str) -> str:
    text = str(text).strip().lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _synonym_score(header_norm: str, synonyms: list[str]) -> float:
    best = 0.0
    for syn in synonyms:
        syn_norm = _normalize(syn)
        if not syn_norm:
            continue
        if header_norm == syn_norm:
            best = max(best, 1.0)
        elif syn_norm in header_norm or header_norm in syn_norm:
            best = max(best, 0.9)
        else:
            best = max(best, SequenceMatcher(None, header_norm, syn_norm).ratio())
    return best


def match_columns(
    headers: list[str | None],
    field_synonyms: dict[str, list[str]],
    threshold: float = COLUMN_MATCH_THRESHOLD,
) -> dict[str, int]:
    """Нечёткое сопоставление заголовков полям — жадно, по убыванию score,
    без повторного использования одной колонки/поля дважды."""
    candidates: list[tuple[float, str, int]] = []
    for field, synonyms in field_synonyms.items():
        for idx, header in enumerate(headers):
            if header is None:
                continue
            score = _synonym_score(_normalize(header), synonyms)
            if score >= threshold:
                candidates.append((score, field, idx))
    candidates.sort(key=lambda t: -t[0])

    result: dict[str, int] = {}
    used_cols: set[int] = set()
    for _score, field, idx in candidates:
        if field in result or idx in used_cols:
            continue
        result[field] = idx
        used_cols.add(idx)
    return result


def match_resource_columns(headers: list[str | None]) -> dict[str, int]:
    """Колонки, названные по классам техники (напр. "Экскаватор, маш-ч") —
    прямой импорт `planned_mh`, если график его уже содержит."""
    result: dict[str, int] = {}
    for idx, header in enumerate(headers):
        if header is None:
            continue
        header_norm = _normalize(header)
        for cls, synonyms in CLASS_RU_SYNONYMS.items():
            if cls in result.values():
                continue
            if any(_normalize(syn) in header_norm for syn in synonyms):
                result[cls] = idx
                break
    return result


def classify_work_type(name: str) -> str | None:
    name_norm = _normalize(name)
    for work_type, keywords in WORK_TYPE_KEYWORDS:
        if any(keyword in name_norm for keyword in keywords):
            return work_type
    return None


def _parse_date_cell(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"не удалось распознать дату: {value!r}")


def _parse_predecessor_token(token: str) -> str | None:
    match = re.match(r"\s*(\d+)", token)
    return match.group(1) if match else None


@dataclass
class ProductivityRef:
    by_work_type: dict[str, dict]

    @classmethod
    def from_json(cls, path: Path) -> ProductivityRef:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(by_work_type={k: v for k, v in raw.items() if not k.startswith("_")})


def derive_planned_mh(
    volume: dict, work_type: str | None, productivity: ProductivityRef
) -> dict[str, float] | None:
    """`planned_mh[c] = qty / productivity_per_mh[c]` (docs/02 §2).

    None, если вид работ не распознан, нормы для него нет, или единица
    измерения в графике не совпадает с единицей нормы — честнее не считать,
    чем посчитать неверно (docs/01-principles.md, правило 4)."""
    if work_type is None or work_type not in productivity.by_work_type:
        return None
    ref = productivity.by_work_type[work_type]
    if volume.get("unit") != ref["unit"]:
        return None
    qty = volume.get("qty")
    if not qty:
        return None
    return {
        cls: round(qty / rate, 2) for cls, rate in ref["productivity_per_mh"].items() if rate > 0
    }


def _resolve_predecessors(entries: list[dict], ref_to_work_id: dict[str, str]) -> None:
    for entry in entries:
        resolved = []
        for token in entry["predecessors"]:
            work_id = ref_to_work_id.get(token, token)
            resolved.append(work_id)
        entry["predecessors"] = resolved


def import_xlsx(
    path: Path,
    *,
    sheet_name: str | None = None,
    zone_map: dict[str, str] | None = None,
    productivity: ProductivityRef | None = None,
) -> list[dict]:
    zone_map = zone_map or {}
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = list(rows[0])
    columns = match_columns(headers, FIELD_SYNONYMS)
    resource_columns = match_resource_columns(headers)

    if "name" not in columns or "start" not in columns or "finish" not in columns:
        raise ValueError(
            f"не удалось распознать обязательные колонки (наименование/начало/окончание) в {path}"
        )

    entries: list[dict] = []
    ref_to_work_id: dict[str, str] = {}
    for row_number, row in enumerate(rows[1:], start=1):
        name = row[columns["name"]]
        if name is None or str(name).strip() == "":
            continue

        work_id = f"W-{row_number:03d}"
        ref_to_work_id[str(row_number)] = work_id

        work_type = classify_work_type(str(name))
        zone_raw = row[columns["zone"]] if "zone" in columns else None
        zone_id = zone_map.get(zone_raw, zone_raw) if zone_raw is not None else None

        qty = row[columns["volume_qty"]] if "volume_qty" in columns else None
        unit = row[columns["volume_unit"]] if "volume_unit" in columns else None
        volume = {"unit": unit, "qty": qty}

        planned_mh = {
            cls: float(row[idx])
            for cls, idx in resource_columns.items()
            if row[idx] not in (None, "")
        }
        if not planned_mh and productivity is not None:
            planned_mh = derive_planned_mh(volume, work_type, productivity) or {}

        predecessors_raw = row[columns["predecessors"]] if "predecessors" in columns else None
        predecessors = []
        if predecessors_raw:
            for token in re.split(r"[;,]", str(predecessors_raw)):
                parsed = _parse_predecessor_token(token)
                if parsed:
                    predecessors.append(parsed)

        entries.append(
            {
                "work_id": work_id,
                "wbs": str(row_number),
                "name": str(name).strip(),
                "work_type": work_type,
                "zone_id": zone_id,
                "start_plan": _parse_date_cell(row[columns["start"]]).isoformat(),
                "finish_plan": _parse_date_cell(row[columns["finish"]]).isoformat(),
                "volume": volume,
                "planned_mh": planned_mh,
                "predecessors": predecessors,
            }
        )

    _resolve_predecessors(entries, ref_to_work_id)
    return entries


def _lookup_ext(
    ext_values: dict[str, str], field_id_by_field: dict[str, str], field: str
) -> str | None:
    field_id = field_id_by_field.get(field)
    return ext_values.get(field_id) if field_id else None


def _local_tag(element: ET.Element) -> str:
    return element.tag.split("}")[-1]


def _extended_attribute_aliases(root: ET.Element) -> dict[str, str]:
    """FieldID -> Alias из глобального словаря пользовательских полей MSPDI."""
    aliases: dict[str, str] = {}
    for ext_attrs in root.iter():
        if _local_tag(ext_attrs) != "ExtendedAttributes":
            continue
        for ext_attr in ext_attrs:
            if _local_tag(ext_attr) != "ExtendedAttribute":
                continue
            field_id, alias = None, None
            for child in ext_attr:
                tag = _local_tag(child)
                if tag == "FieldID":
                    field_id = child.text
                elif tag == "Alias":
                    alias = child.text
            if field_id and alias:
                aliases[field_id] = alias
    return aliases


def import_msp_xml(
    path: Path,
    *,
    zone_map: dict[str, str] | None = None,
    productivity: ProductivityRef | None = None,
) -> list[dict]:
    zone_map = zone_map or {}
    root = ET.parse(path).getroot()

    aliases = _extended_attribute_aliases(root)
    alias_field_ids = list(aliases.keys())
    alias_headers = list(aliases.values())
    matched = match_columns(alias_headers, FIELD_SYNONYMS)
    field_id_by_field = {field: alias_field_ids[idx] for field, idx in matched.items()}

    entries: list[dict] = []
    ref_to_work_id: dict[str, str] = {}
    uid_to_work_id: dict[str, str] = {}

    tasks_root = None
    for element in root.iter():
        if _local_tag(element) == "Tasks":
            tasks_root = element
            break
    if tasks_root is None:
        return []

    row_number = 0
    for task in tasks_root:
        if _local_tag(task) != "Task":
            continue
        fields: dict[str, str | None] = {}
        uid = None
        ext_values: dict[str, str] = {}
        predecessor_uids: list[str] = []
        for child in task:
            tag = _local_tag(child)
            if tag == "UID":
                uid = child.text
            elif tag in ("Name", "Start", "Finish"):
                fields[tag] = child.text
            elif tag == "ExtendedAttribute":
                field_id, value = None, None
                for sub in child:
                    sub_tag = _local_tag(sub)
                    if sub_tag == "FieldID":
                        field_id = sub.text
                    elif sub_tag == "Value":
                        value = sub.text
                if field_id and value is not None:
                    ext_values[field_id] = value
            elif tag == "PredecessorLink":
                for sub in child:
                    if _local_tag(sub) == "PredecessorUID" and sub.text:
                        predecessor_uids.append(sub.text)

        name = fields.get("Name")
        if not name or not fields.get("Start") or not fields.get("Finish"):
            continue

        row_number += 1
        work_id = f"W-{row_number:03d}"
        if uid:
            uid_to_work_id[uid] = work_id
        ref_to_work_id[str(row_number)] = work_id

        work_type = classify_work_type(name)

        zone_raw = _lookup_ext(ext_values, field_id_by_field, "zone")
        zone_id = zone_map.get(zone_raw, zone_raw) if zone_raw is not None else None
        qty_raw = _lookup_ext(ext_values, field_id_by_field, "volume_qty")
        volume = {
            "unit": _lookup_ext(ext_values, field_id_by_field, "volume_unit"),
            "qty": float(qty_raw) if qty_raw not in (None, "") else None,
        }

        planned_mh: dict[str, float] = {}
        if productivity is not None:
            planned_mh = derive_planned_mh(volume, work_type, productivity) or {}

        entries.append(
            {
                "work_id": work_id,
                "wbs": str(row_number),
                "name": name.strip(),
                "work_type": work_type,
                "zone_id": zone_id,
                "start_plan": _parse_date_cell(fields["Start"][:10]).isoformat(),
                "finish_plan": _parse_date_cell(fields["Finish"][:10]).isoformat(),
                "volume": volume,
                "planned_mh": planned_mh,
                "predecessors": list(predecessor_uids),
            }
        )

    for entry in entries:
        entry["predecessors"] = [
            uid_to_work_id.get(p, ref_to_work_id.get(p, p)) for p in entry["predecessors"]
        ]

    return entries


def write_schedule_json(entries: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
