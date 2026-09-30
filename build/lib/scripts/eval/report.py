"""Рендер `docs/04-metrics.md` + PNG-графики в `docs/img/`.

Единственный писатель этого файла — `scripts/eval_end2end.py` (докстринг
самого `docs/04-metrics.md`): числа сюда попадают только из реального
прогона, никогда руками.
"""
from __future__ import annotations

import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from scripts.eval.detection_metrics import ClassDetectionMetrics
from scripts.eval.deviations_metrics import DeviationEvaluation
from scripts.eval.machine_hours_metrics import MachineHoursError
from scripts.eval.performance import PerformanceEstimate
from scripts.eval.state_metrics import StateEvaluation
from scripts.eval.tracking_metrics import TrackingMetrics


def _fmt(value: float | None, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}{suffix}"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:  # noqa: BLE001 — репозиторий может быть не под git локально
        return "—"


def save_charts(
    img_dir: Path,
    *,
    state_eval: StateEvaluation,
    predicted_rows: list[dict],
    truth_rows: list[dict],
    deviation_eval: DeviationEvaluation,
) -> dict[str, str]:
    """Возвращает {ключ: путь относительно docs/} для вставки в markdown."""
    img_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    fig, ax = plt.subplots(figsize=(4, 4))
    im = ax.imshow(state_eval.confusion, cmap="Blues")
    ax.set_xticks(range(len(state_eval.labels)))
    ax.set_yticks(range(len(state_eval.labels)))
    ax.set_xticklabels(state_eval.labels)
    ax.set_yticklabels(state_eval.labels)
    ax.set_xlabel("Предсказано")
    ax.set_ylabel("Истина")
    for i in range(len(state_eval.labels)):
        for j in range(len(state_eval.labels)):
            ax.text(j, i, str(state_eval.confusion[i, j]), ha="center", va="center")
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(img_dir / "state_confusion_matrix.png", dpi=140)
    plt.close(fig)
    paths["state_confusion"] = "img/state_confusion_matrix.png"

    pred_by_date: dict[str, float] = defaultdict(float)
    truth_by_date: dict[str, float] = defaultdict(float)
    for r in predicted_rows:
        pred_by_date[r["date"]] += r["mh_active"]
    for r in truth_rows:
        truth_by_date[r["date"]] += r["mh_active"]
    dates = sorted(set(pred_by_date) | set(truth_by_date))

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(dates, [truth_by_date[d] for d in dates], label="Истина (ground truth)", marker="o")
    ax.plot(dates, [pred_by_date[d] for d in dates], label="Пайплайн (предсказано)", marker="x")
    ax.set_ylabel("mh_active, ч/сут (сумма по зонам и классам)")
    ax.legend()
    ax.tick_params(axis="x", rotation=60, labelsize=7)
    fig.tight_layout()
    fig.savefig(img_dir / "mh_active_predicted_vs_truth.png", dpi=140)
    plt.close(fig)
    paths["mh_active"] = "img/mh_active_predicted_vs_truth.png"

    labels = [m.type for m in deviation_eval.by_type]
    precisions = [m.precision or 0 for m in deviation_eval.by_type]
    recalls = [m.recall or 0 for m in deviation_eval.by_type]
    x = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(x - width / 2, precisions, width, label="Precision")
    ax.bar(x + width / 2, recalls, width, label="Recall")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.legend()
    fig.tight_layout()
    fig.savefig(img_dir / "deviation_precision_recall.png", dpi=140)
    plt.close(fig)
    paths["deviations"] = "img/deviation_precision_recall.png"

    return paths


def render_markdown(
    *,
    detection: list[ClassDetectionMetrics] | None,
    tracking: TrackingMetrics | None,
    state_eval: StateEvaluation,
    mh_error: MachineHoursError,
    deviation_eval: DeviationEvaluation,
    performance: PerformanceEstimate,
    benchmark_days: int,
    chart_paths: dict[str, str],
) -> str:
    now = datetime.now(UTC).astimezone().isoformat(timespec="seconds")

    if detection:
        detection_rows = "\n".join(
            f"| {m.cls} | {m.n_images} | {_fmt(m.map50)} | {_fmt(m.map50_95)} "
            f"| {_fmt(m.precision)} | {_fmt(m.recall)} |"
            for m in detection
        )
        detection_note = ""
    else:
        detection_rows = "| — | — | — | — | — | — |"
        detection_note = (
            "\n> Весов детектора нет в репозитории (`models/`) — раздел не может "
            "быть посчитан. Появятся веса — `eval_end2end.py` заполнит эти строки "
            "автоматически (см. `scripts/eval/detection_metrics.py`).\n"
        )

    if tracking:
        tracking_table = (
            "| Метрика | Значение | Цель |\n"
            "|---|---|---|\n"
            f"| MOTA | {_fmt(tracking.mota)} | ≥ 0.70 |\n"
            f"| IDF1 | {_fmt(tracking.idf1)} | ≥ 0.70 |\n"
            f"| Переключений ID | {tracking.id_switches} | ≤ 2 на трек |\n"
        )
        tracking_note = ""
    else:
        tracking_table = (
            "| Метрика | Значение | Цель |\n"
            "|---|---|---|\n"
            "| MOTA | — | ≥ 0.70 |\n"
            "| IDF1 | — | ≥ 0.70 |\n"
            "| Переключений ID | — | ≤ 2 на трек |\n"
        )
        tracking_note = "\n> Весов детектора нет — трекер не запускался.\n"

    state_rows = "\n".join(
        f"| {m.state} | {_fmt(m.precision)} | {_fmt(m.recall)} | {_fmt(m.f1)} | {m.support} |"
        for m in state_eval.by_state
        if m.state in ("active", "idle")
    )

    dev_rows = "\n".join(
        f"| {m.type} | {m.expected} | {m.matched} | {m.detected - m.matched} "
        f"| {_fmt(m.precision)} | {_fmt(m.recall)} | {_fmt(m.f1)} | {_fmt(m.mean_delay_days, 1)} |"
        for m in deviation_eval.by_type
    )
    overall = deviation_eval.overall

    return f"""\
# Метрики качества

> Этот файл заполняется ТОЛЬКО скриптом `scripts/eval_end2end.py`.
> Руками сюда числа не пишем. Если число попало в презентацию, но его
> нет здесь — на питче его называть нельзя.

Дата последнего прогона: `{now}`
Коммит: `{_git_commit()}`
Бенчмарк: `data/benchmark/` ({benchmark_days} суток).
Внедрённые отклонения — `expected_deviations.jsonl`.

---

## 1. Детекция техники

| Класс | Изображений в тесте | mAP@50 | mAP@50-95 | Precision | Recall |
|---|---|---|---|---|---|
{detection_rows}
{detection_note}
Цель: mAP@50 ≥ 0.80 по ключевым классам.

## 2. Трекинг

{tracking_table}
{tracking_note}
## 3. Состояние «работает / простаивает»

| Состояние | Precision | Recall | F1 | Примеров в тесте |
|---|---|---|---|---|
{state_rows}

Accuracy (все состояния, включая `parked`): {_fmt(state_eval.accuracy)}
(обучено на {state_eval.n_train} примерах, проверено на {state_eval.n_test})

Ориентир — опубликованный результат Edge-IMI (YOLOv8 + ByteTrack +
логистическая регрессия на признаках bbox): Accuracy 0.79, F1 (active) 0.76.
Наш прирост должен объясняться добавлением оптического потока и цветовой
дисперсии внутри бокса.

> Таблица выше — качество классификатора на отложенной выборке из ТЕХ ЖЕ
> синтетических распределений признаков, на которых он обучен (см.
> `services/perception/state.py`). Это проверяет саму модель, но не то, что
> происходит на реальных пикселях: раздел 4 использует признаки, честно
> посчитанные с рендеренных кадров (`scripts/eval/pipeline_run.py`), и там
> расхождение с ground truth заметно больше — разрыв между "модель обучена
> верно" и "спрайты синтетики дают реалистичные признаки" виден именно там.

![Матрица ошибок классификатора состояния]({chart_paths["state_confusion"]})

## 4. Машино-часы — главная метрика продукта

| Метрика | Значение | Цель |
|---|---|---|
| MAE суточных `mh_active`, ч | {_fmt(mh_error.mae_active_hours)} | ≤ 0.5 |
| MAPE суточных `mh_active`, % | {_fmt(mh_error.mape_active_pct, 1)} | ≤ 10 |
| MAE `mh_present`, ч | {_fmt(mh_error.mae_present_hours)} | ≤ 0.3 |
| Смещение (систематическая ошибка), ч | {_fmt(mh_error.bias_active_hours)} | \\|bias\\| ≤ 0.2 |

Сравнение по {mh_error.n_rows} строкам (дата × зона × класс). Боксы и классы
здесь — ground truth (детектора ещё нет, раздел 1); ошибка отражает только
классификатор состояния на РЕАЛЬНЫХ признаках с кадров, не качество детекции.

> Большие MAE/MAPE здесь — честный сигнал, а не баг агрегации: спрайты
> синтетики (`scripts/synth/sprites.py`) — статичные цветные иконки, и их
> HSV-дисперсия и оптический поток на реальных пикселях не совпадают с
> распределениями, на которых обучен классификатор (раздел 3). Чтобы это
> число снизилось, спрайтам нужна текстура/анимация, реально коррелирующая
> с состоянием — это работа над `scripts/synth/`, не над `state.py`.

![Машино-часы: пайплайн против ground truth]({chart_paths["mh_active"]})

## 5. Выявление отклонений — главная метрика ценности

| Тип | Внедрено | Найдено | Ложных | Precision | Recall | Задержка, сут |
|---|---|---|---|---|---|---|
{dev_rows}
| **Всего** | {overall.expected} | {overall.matched} | {overall.detected - overall.matched} \
| {_fmt(overall.precision)} | {_fmt(overall.recall)} | {_fmt(overall.mean_delay_days, 1)} |

Цель: Precision ≥ 0.85, Recall ≥ 0.80, средняя задержка ≤ 2 суток.

Precision важнее Recall: ложное отклонение подрывает доверие к системе
у прораба, пропущенное — обнаружится на следующие сутки.

> Пропуски по Р1 (дефицит) и Р2 (простой) ожидаемы и объяснимы разделом 4:
> оба правила сравнивают фактические машино-часы работы с планом/порогом, и
> если классификатор на реальных признаках почти всё относит к "active",
> фактическая активность завышена — дефицит и простой маскируются одним и
> тем же разрывом "спрайты без текстуры/анимации". На самом ground truth
> (без искажения классификатором) полнота выше — см.
> `tests/test_eval_deviations_metrics.py`; правила Р1/Р2 при этом всё равно
> иногда конкурируют между собой (приоритет отдаётся Р1) — это отдельное,
> уже не связанное с детекцией ограничение текущей логики приоритетов
> (`services/analytics/deviations.py`).

![Precision/Recall по типам отклонений]({chart_paths["deviations"]})

## 6. Устойчивость

| Условие | Доля кадров | Что делает система | Ложных отклонений |
|---|---|---|---|
| Ночь | | помечает low confidence | должно быть 0 |
| Дождь / туман | | | |
| Частичное перекрытие | | | |
| Припаркованная техника | | не учитывает в МЧ | |

## 7. Производительность и стоимость

| Метрика | Значение |
|---|---|
| Кадров/сек, CPU (перцепция без детектора) | {_fmt(performance.fps_cpu_perception_only, 1)} |
| Время обработки 1 камеро-суток, с | {_fmt(performance.seconds_per_camera_day, 1)} |
| Оценочная стоимость 1 камеро-суток, ₽ | {_fmt(performance.cost_per_camera_day_rub, 2)} |
| Оценка на 1000 камер в сутки, ₽ | {_fmt(performance.cost_per_1000_cameras_per_day_rub, 0)} |

> Время инференса детектора (YOLO) в кадры/сек выше не входит — весов ещё
> нет (см. раздел 1). Ставка CPU-часа — допущение
> (`scripts/eval/performance.py::CPU_HOUR_COST_RUB`), требует уточнения
> перед публикацией на питче.

## 8. Экономический эффект

Формула, а не круглое число:

```
Потери от простоя = Σ_техника ( mh_idle × стоимость_машино_часа )
Эффект            = Потери × доля_устранимых_простоев
```

| Параметр | Значение | Источник |
|---|---|---|
| Стоимость машино-часа по классам | | `data/ref/machine_hour_cost.json`, указать источник |
| Наблюдаемый КИТ на бенчмарке | | расчёт |
| Доля устранимых простоев | | допущение, обосновать |

Каждое число в этой таблице на питче должно иметь ответ на вопрос
«откуда вы это взяли». Если ответа нет — число из презентации убрать.
"""
