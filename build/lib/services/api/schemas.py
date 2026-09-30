"""Pydantic v2 модели ответов/запросов — 1:1 с контрактами `docs/02-data-contract.md`.

Поля и описания на русском: страница `/docs` (OpenAPI) показывается экспертам
на питче (`docs/05-pitch.md`) — она должна читаться как документация для
человека, а не как дамп внутренних типов.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# objects.json (docs/02, §1)
# ---------------------------------------------------------------------------


class ZoneOut(BaseModel):
    zone_id: str = Field(description="Идентификатор зоны выполнения работ")
    title: str = Field(default="", description="Человекочитаемое название зоны")
    polygon: list[list[float]] = Field(description="Полигон зоны на кадре, [[x,y], ...]")
    area_m2: float | None = Field(default=None, description="Площадь зоны, м²")


class CameraOut(BaseModel):
    camera_id: str = Field(description="Идентификатор камеры")
    title: str = Field(default="", description="Название ракурса")
    source_kind: str = Field(description="Тип источника: rtsp | hls | folder | replay")
    source_uri: str = Field(description="Адрес источника кадров")
    capture_interval_sec: int = Field(description="Номинальный интервал съёмки, сек")
    zones: list[ZoneOut] = Field(
        default_factory=list, description="Зоны выполнения работ этой камеры"
    )


class ObjectOut(BaseModel):
    object_id: str = Field(description="Идентификатор объекта строительства")
    name: str = Field(description="Название объекта")
    address: str = Field(default="", description="Адрес объекта")
    timezone: str = Field(default="Europe/Moscow", description="Часовой пояс объекта")


class ObjectDetailOut(ObjectOut):
    cameras: list[CameraOut] = Field(default_factory=list, description="Камеры объекта")


# ---------------------------------------------------------------------------
# detections.jsonl (docs/02, §3) — используется эндпоинтом /live и /replay
# ---------------------------------------------------------------------------


class QualityOut(BaseModel):
    blur: float = Field(description="Размытость кадра, 0 — резкий, 1 — сильно размыт")
    night: bool = Field(description="Признак ночного кадра")
    occlusion: float = Field(description="Доля кадра, закрытая помехой (грязный объектив и т.п.)")
    score: float = Field(description="Итоговая оценка качества кадра, 0..1")


class FeaturesOut(BaseModel):
    centroid_mad: float = Field(description="MAD смещения центра нижней грани бокса за окно")
    area_mad: float = Field(description="MAD площади бокса за окно")
    flow_mag: float = Field(description="Средняя величина оптического потока внутри бокса")
    hsv_var: float = Field(description="Пространственная дисперсия HSV внутри бокса")


class DetectedObjectOut(BaseModel):
    track_id: int = Field(description="Стабильный идентификатор трека")
    cls: str = Field(description="Класс техники")
    conf: float = Field(description="Уверенность детектора, 0..1")
    bbox: list[float] = Field(description="Бокс [x, y, ширина, высота] в пикселях кадра")
    zone_id: str | None = Field(default=None, description="Зона, в которой находится техника")
    state: str = Field(description="Состояние: active | idle | parked | unknown")
    state_conf: float = Field(description="Уверенность классификатора состояния, 0..1")
    features: FeaturesOut


class DetectionFrameOut(BaseModel):
    camera_id: str = Field(description="Камера, снявшая кадр")
    ts: str = Field(description="Время кадра, ISO 8601, +03:00")
    frame_uri: str = Field(description="Путь к файлу кадра")
    quality: QualityOut
    objects: list[DetectedObjectOut] = Field(default_factory=list)


class LiveStateOut(BaseModel):
    object_id: str = Field(description="Идентификатор объекта")
    ts: str = Field(description="Время формирования ответа, ISO 8601")
    cameras: list[DetectionFrameOut] = Field(
        default_factory=list, description="Последний известный кадр по каждой камере объекта"
    )


# ---------------------------------------------------------------------------
# schedule.json (docs/02, §2)
# ---------------------------------------------------------------------------


class VolumeOut(BaseModel):
    unit: str | None = Field(default=None, description="Единица измерения объёма работ")
    qty: float | None = Field(default=None, description="Объём работ в этой единице")


class ScheduleWorkOut(BaseModel):
    work_id: str = Field(description="Идентификатор работы")
    wbs: str = Field(default="", description="Номер в иерархии графика (WBS)")
    name: str = Field(description="Наименование работы")
    work_type: str | None = Field(default=None, description="Вид работ (ресурсный отпечаток)")
    zone_id: str | None = Field(default=None, description="Зона выполнения")
    start_plan: str = Field(description="Плановая дата начала")
    finish_plan: str = Field(description="Плановая дата окончания")
    volume: VolumeOut
    planned_mh: dict[str, float] = Field(
        default_factory=dict, description="Плановые машино-часы по классам техники"
    )
    predecessors: list[str] = Field(default_factory=list, description="Работы-предшественники")


class ScheduleImportResult(BaseModel):
    object_id: str = Field(description="Объект, для которого импортирован график")
    imported_count: int = Field(description="Число импортированных работ")
    works: list[ScheduleWorkOut] = Field(description="Импортированные работы")


# ---------------------------------------------------------------------------
# machine_hours.jsonl / work_progress.jsonl (docs/02, §4-5) — /gantt, /economics
# ---------------------------------------------------------------------------


class WorkProgressOut(BaseModel):
    date: str = Field(description="Дата, на которую посчитан прогресс")
    work_id: str = Field(description="Идентификатор работы")
    name: str = Field(description="Наименование работы")
    mh_plan_to_date: float = Field(description="План машино-часов нарастающим итогом")
    mh_fact_to_date: float = Field(description="Факт машино-часов нарастающим итогом")
    spi: float = Field(description="Индекс выполнения по срокам = факт / план")
    rate_mh_per_day: float = Field(description="Текущий темп, маш.-ч/сут")
    forecast_finish: str | None = Field(default=None, description="Прогнозная дата завершения")
    delay_days: int | None = Field(default=None, description="Прогнозное отставание, суток")
    status: str = Field(description="Светофор: green | yellow | red")


class GanttOut(BaseModel):
    object_id: str
    period: dict[str, str] = Field(description="Запрошенный период {from, to}")
    works: list[WorkProgressOut]


class UtilizationRowOut(BaseModel):
    zone_id: str
    cls: str = Field(description="Класс техники")
    mh_present: float = Field(description="Часы присутствия на площадке")
    mh_active: float = Field(description="Часы фактической работы")
    mh_idle: float = Field(description="Часы простоя")
    utilization: float = Field(description="КИТ = mh_active / mh_present")
    idle_cost_rub: float = Field(description="Стоимость простоя, ₽")


class EconomicsOut(BaseModel):
    object_id: str
    period: dict[str, str] = Field(description="Запрошенный период {from, to}")
    currency: str = Field(default="RUB")
    total_idle_cost_rub: float = Field(description="Суммарные потери от простоя за период, ₽")
    by_class: list[UtilizationRowOut]


# ---------------------------------------------------------------------------
# deviations.jsonl (docs/02, §6)
# ---------------------------------------------------------------------------


class PeriodOut(BaseModel):
    from_: str = Field(alias="from", description="Начало периода отклонения")
    to: str = Field(description="Конец периода отклонения")

    model_config = {"populate_by_name": True}


class ImpactOut(BaseModel):
    spi: float | None = Field(
        default=None, description="Индекс выполнения по срокам на момент детекции"
    )
    delay_days: int | None = Field(default=None, description="Прогнозное отставание, суток")
    idle_cost_rub: float = Field(default=0.0, description="Стоимость простоя за период, ₽")


class EvidenceOut(BaseModel):
    frames: list[str] = Field(default_factory=list, description="Кадры-улики")
    chart: str = Field(default="mh_plan_vs_fact", description="Какой график показать в карточке")
    confidence: float = Field(description="Уверенность системы в отклонении, 0..1")


class DeviationOut(BaseModel):
    deviation_id: str = Field(description="Идентификатор отклонения")
    detected_at: str = Field(description="Когда отклонение обнаружено, ISO 8601")
    period: PeriodOut
    work_id: str | None = Field(
        default=None, description="Работа графика, к которой относится отклонение"
    )
    zone_id: str = Field(description="Зона, в которой обнаружено отклонение")
    type: str = Field(
        description="Тип: R0_low_confidence | R1_resource_gap | R2_idle | "
        "R3_front_mismatch | R4_silence"
    )
    severity: str = Field(description="Серьёзность: low | medium | high")
    observed: dict = Field(
        default_factory=dict, description="Факт (числа плана/факта по контексту типа)"
    )
    expected: dict = Field(default_factory=dict, description="План/ожидание по контексту типа")
    impact: ImpactOut
    explanation: str = Field(description="Формулировка на русском для прораба")
    recommendation: str = Field(description="Рекомендация на русском")
    evidence: EvidenceOut
    status: str = Field(default="open", description="open — новое, acted — по нему сформирован акт")


class ActResult(BaseModel):
    deviation_id: str = Field(description="Отклонение, по которому сформирован акт")
    generated_at: str = Field(description="Когда акт сформирован")
    content_type: str = Field(default="application/pdf")


# ---------------------------------------------------------------------------
# /api/cameras/{id}/zones (docs/02, §7)
# ---------------------------------------------------------------------------


class ZoneIn(BaseModel):
    zone_id: str = Field(description="Идентификатор зоны")
    title: str = Field(default="", description="Название зоны")
    polygon: list[list[float]] = Field(description="Полигон зоны на кадре, [[x,y], ...]")
    area_m2: float | None = Field(default=None, description="Площадь зоны, м²")


class ZonesUpdateResult(BaseModel):
    camera_id: str
    zones: list[ZoneOut]
