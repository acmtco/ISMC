"""PDF-акт по отклонению — `POST /api/deviations/{id}/act` (docs/02, §7).

Простой однострочный акт, не бланк со штампами: формулировка, числа плана и
факта, рекомендация — то же, что и в карточке отклонения (CLAUDE.md, правило
5), только оформленное как документ, который можно приложить к переписке
с подрядчиком. Формулировки — на русском, поэтому шрифт по умолчанию не
подходит: используем DejaVu Sans (`data/ref/fonts/`, лицензия — см.
`LICENSE_DEJAVU.txt` там же, свободно для встраивания).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from services.api.models_db import DeviationRecord

FONT_DIR = Path("data/ref/fonts")

TYPE_TITLES = {
    "R0_low_confidence": "недостаточно данных",
    "R1_resource_gap": "ресурсный дефицит",
    "R2_idle": "простой техники",
    "R3_front_mismatch": "несоответствие фронта работ",
    "R4_silence": "отсутствие техники",
}


def _pdf_with_cyrillic_font(font_dir: Path = FONT_DIR) -> FPDF:
    pdf = FPDF()
    pdf.add_font("DejaVu", "", str(font_dir / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(font_dir / "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    return pdf


def render_act_pdf(
    record: DeviationRecord, generated_at: datetime, font_dir: Path = FONT_DIR
) -> bytes:
    pdf = _pdf_with_cyrillic_font(font_dir)

    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 10, f"Акт по отклонению {record.deviation_id}", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("DejaVu", "", 11)
    title = TYPE_TITLES.get(record.type, record.type)
    lines = [
        f"Сформирован: {generated_at.isoformat()}",
        f"Тип отклонения: {record.type} ({title})",
        f"Зона: {record.zone_id}",
        f"Работа: {record.work_id or '—'}",
        f"Период: {record.period_from} – {record.period_to}",
        f"Серьёзность: {record.severity}",
        "",
        record.explanation,
        "",
        f"Рекомендация: {record.recommendation}",
    ]
    for line in lines:
        # без new_x/new_y `multi_cell` не возвращает x к левому полю — x копится
        # вправо с каждой строкой, пока не кончится место на странице.
        pdf.multi_cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
