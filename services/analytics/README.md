# services/analytics

Слой аналитики: график → машино-часы → матчинг → отклонения → прогноз → экономика.

## Модули

- `schedule_io.py` — импорт графика (XLSX / MS Project XML) в `schedule.json`;
  нечёткое сопоставление заголовков колонок, вывод `planned_mh` из объёма и
  `data/ref/productivity.json`, если в источнике его нет.
- `machine_hours.py` — агрегация `detections.jsonl` в суточные машино-часы
  (`aggregate_machine_hours`) и покрытие/уверенность по суткам
  (`daily_quality`), с учётом `quality.score` и исключением `parked`/`unknown`
  из машино-часов.
- `matching.py` — ресурсный отпечаток вида работ и `match_score`
  (docs/03, §1-2), веса — `config/matching.yaml`.
- `deviations.py` — правила Р0-Р4 (docs/03, §3), пороги — `config/thresholds.yaml`;
  `DeviationEngine.run()` возвращает записи `deviations.jsonl` с
  формулировками на русском.
- `forecast.py` — SPI, темп, прогнозная дата, `delay_days`, обратная задача
  "сколько техники добавить, чтобы успеть" (docs/03, §4).
- `economics.py` — КИТ, часы простоя, стоимость простоя —
  `data/ref/machine_hour_cost.json`.
- `ru_text.py` — русские названия классов техники с согласованием числительных.

Вход: `detections.jsonl` (`services/perception`), `objects.json`, `schedule.json`,
`data/ref/work_signatures.json`, `data/ref/productivity.json`,
`data/ref/machine_hour_cost.json`, `config/matching.yaml`, `config/thresholds.yaml`.

Выход: `machine_hours.jsonl`, `deviations.jsonl` — форматы в
`docs/02-data-contract.md`, правила — `docs/03-deviation-rules.md`.

Все пороги и веса — в конфигах, ни одного магического числа в коде.
`services/api` (следующий слой) вызывает эти модули напрямую как библиотеку.
