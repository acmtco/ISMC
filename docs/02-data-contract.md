# Контракты данных

Это главный документ проекта. Модули не знают друг о друге ничего, кроме
этих схем. Любой участник команды может писать свой модуль параллельно.

Все времена — ISO 8601 с таймзоной `+03:00` (Москва). Все идентификаторы — строки.

---

## 1. `objects.json` — паспорт объекта строительства

```json
{
  "object_id": "OBJ-001",
  "name": "Жилой комплекс, корпус 3",
  "address": "г. Москва, ...",
  "timezone": "Europe/Moscow",
  "cameras": [
    {
      "camera_id": "CAM-01",
      "title": "Северный ракурс",
      "source": {"kind": "replay", "uri": "data/replay/CAM-01/"},
      "capture_interval_sec": 20,
      "zones": [
        {
          "zone_id": "Z-PIT",
          "title": "Котлован",
          "polygon": [[120, 480], [900, 470], [960, 780], [80, 800]],
          "area_m2": 2400
        }
      ],
      "homography": null
    }
  ]
}
```

`source.kind` ∈ `rtsp` | `hls` | `folder` | `replay`.
`homography` — опциональная матрица 3×3 «кадр → генплан», если размечены 4 точки.

---

## 2. `schedule.json` — нормализованный календарный график

Импортируется из XLSX / MS Project XML. Ключевое поле — `planned_mh`:
плановая потребность в машино-часах по типам техники.

```json
[
  {
    "work_id": "W-014",
    "wbs": "2.1.3",
    "name": "Разработка котлована",
    "work_type": "earthworks_excavation",
    "zone_id": "Z-PIT",
    "start_plan": "2026-09-15",
    "finish_plan": "2026-10-02",
    "volume": {"unit": "м3", "qty": 12000},
    "planned_mh": {"excavator": 180.0, "dump_truck": 420.0, "bulldozer": 60.0},
    "predecessors": ["W-011"]
  }
]
```

Если в исходном графике нет `planned_mh`, аналитик выводит их из объёма
и нормы производительности: `planned_mh = qty / productivity_per_mh`.
Справочник норм — `data/ref/productivity.json`.

---

## 3. `detections.jsonl` — выход слоя восприятия, одна строка на кадр

```json
{
  "camera_id": "CAM-01",
  "ts": "2026-09-20T08:30:00+03:00",
  "frame_uri": "data/replay/CAM-01/20260920T083000.jpg",
  "quality": {"blur": 0.12, "night": false, "occlusion": 0.03, "score": 0.94},
  "objects": [
    {
      "track_id": 17,
      "cls": "excavator",
      "conf": 0.91,
      "bbox": [412, 388, 180, 120],
      "zone_id": "Z-PIT",
      "state": "active",
      "state_conf": 0.83,
      "features": {"centroid_mad": 4.7, "area_mad": 311.0, "flow_mag": 1.94, "hsv_var": 480.0}
    }
  ]
}
```

`cls` ∈ `excavator` | `dump_truck` | `concrete_mixer` | `concrete_pump` |
`tower_crane` | `mobile_crane` | `bulldozer` | `roller` | `loader` |
`drilling_rig` | `worker`

`state` ∈ `active` | `idle` | `parked` | `unknown`

`features` считаются в скользящем окне 90 секунд по треку: `centroid_mad` —
MAD смещения центра нижней грани бокса, `area_mad` — MAD площади бокса,
`flow_mag` — средняя величина оптического потока Фарнебака внутри бокса
между соседними кадрами, `hsv_var` — дисперсия HSV-гистограммы внутри
бокса (текстура/цветовая изменчивость: работающий двигатель и движущиеся
части дают более "шумную" картинку, чем стоящая техника).

**Правило качества:** если `quality.score < 0.5`, кадр помечается и
исключается из расчёта машино-часов; интервал интерполируется, но окно
получает `confidence: low`.

---

## 4. `machine_hours.jsonl` — суточный агрегат (ядро системы)

```json
{
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
  "confidence": 0.88
}
```

`coverage` — доля суток, покрытая пригодными кадрами. Ниже 0.6 —
отклонения по этой зоне не формируются.

---

## 5. `work_progress.jsonl` — сопоставление факта с графиком

```json
{
  "date": "2026-09-20",
  "work_id": "W-014",
  "match_score": 0.87,
  "mh_plan_to_date": 92.0,
  "mh_fact_to_date": 61.5,
  "spi": 0.67,
  "rate_mh_per_day": 12.3,
  "forecast_finish": "2026-10-09",
  "delay_days": 7,
  "status": "red"
}
```

`match_score` — насколько наблюдаемый ресурсный отпечаток похож на
ожидаемый для этой работы (см. `docs/03-deviation-rules.md`).

---

## 6. `deviations.jsonl` — то, что видит руководитель

```json
{
  "deviation_id": "D-0007",
  "detected_at": "2026-09-20T19:05:00+03:00",
  "period": {"from": "2026-09-18", "to": "2026-09-20"},
  "work_id": "W-014",
  "zone_id": "Z-PIT",
  "type": "R1_resource_gap",
  "severity": "high",
  "observed": {"excavator": 1, "dump_truck": 2},
  "expected": {"excavator": 2, "dump_truck": 5},
  "impact": {"spi": 0.67, "delay_days": 7, "idle_cost_rub": 0},
  "explanation": "Третьи сутки на котловане работает 1 экскаватор из 2 плановых и 2 самосвала из 5. Фактический темп 12,3 маш.-ч/сут при плановых 18,4. При сохранении темпа работа завершится 09.10 вместо 02.10.",
  "recommendation": "Вывести на объект 1 экскаватор и 3 самосвала до 24.09 либо согласовать сдвиг срока.",
  "evidence": {
    "frames": ["data/replay/CAM-01/20260920T101000.jpg"],
    "chart": "mh_plan_vs_fact",
    "confidence": 0.88
  }
}
```

`type` ∈
- `R1_resource_gap` — техники меньше плановой потребности
- `R2_idle` — техника присутствует, но простаивает
- `R3_front_mismatch` — работает не та техника / не в той зоне / не в то время
- `R4_silence` — по графику работа идёт, техники нет вовсе
- `R0_low_confidence` — служебный: система не может судить

---

## 7. REST API (FastAPI)

```
GET  /api/objects                          список объектов
GET  /api/objects/{id}/live                текущее состояние площадки
GET  /api/objects/{id}/gantt?from=&to=     план vs факт по работам
GET  /api/objects/{id}/deviations?type=    лента отклонений
GET  /api/deviations/{id}                  карточка с доказательствами
POST /api/deviations/{id}/act              сформировать PDF-акт
GET  /api/objects/{id}/economics?from=&to= КИТ, простои, рубли
POST /api/objects/{id}/schedule            импорт графика (xlsx)
POST /api/cameras/{id}/zones               сохранить полигоны зон
GET  /api/objects/{id}/replay?speed=       управление «машиной времени»
```

Все ответы — Pydantic-модели, сгенерированные из этих схем.
OpenAPI-схема доступна на `/docs` — показать её эксперту на питче.
