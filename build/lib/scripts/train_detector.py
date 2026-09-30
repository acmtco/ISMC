"""Дообучение YOLO11 на строительной технике (ТЗ, раздел 3.2: «использование
готовых моделей для обнаружения объектов и их дообучение»).

Датасет собирается из двух источников, оба — локальные папки, скачивание
внутри скрипта не выполняется (docs/01-principles.md, правило 2):

- открытый размеченный набор в YOLO-формате (`--yolo-dir`): пары
  `<имя>.jpg` + `<имя>.txt`, где txt — строки `cls cx cy w h` в долях кадра;
- собственная разметка снимков ДГП (`--extra-dir`), когда она появится, в
  том же формате.

Класс в исходном наборе может не совпадать с нашим перечнем (docs/02 §3):
`--class-map` переназначает индексы, например `0=excavator`.

Результат — `models/yolo11n_construction.pt`, путь к которому ждёт
`config/perception.yaml`. Метрики печатаются в консоль и сохраняются
ultralytics в `runs/`; в `docs/04-metrics.md` они попадают только через
`scripts/eval_end2end.py` (docs/01-principles.md, Definition of Done).
"""
from __future__ import annotations

import argparse
import random
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from services.perception.classes import DETECTION_CLASSES

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")


def _pairs(directory: Path) -> list[tuple[Path, Path]]:
    """Пары (изображение, разметка). Снимки без txt пропускаются молча —
    это кадры, до которых разметка ещё не дошла, а не ошибка."""
    found = []
    for image in sorted(directory.rglob("*")):
        if image.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        label = image.with_suffix(".txt")
        if label.exists():
            found.append((image, label))
    return found


def _remap_label(text: str, class_map: dict[int, int]) -> str:
    """Переназначение индексов классов. Строки с классом, которого нет в
    `class_map`, выбрасываются — иначе чужой индекс молча стал бы нашим."""
    lines = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        source_cls = int(parts[0])
        if source_cls not in class_map:
            continue
        lines.append(" ".join([str(class_map[source_cls]), *parts[1:]]))
    return "\n".join(lines) + ("\n" if lines else "")


def build_dataset(
    sources: list[tuple[Path, dict[int, int]]],
    out_dir: Path,
    *,
    val_share: float,
    seed: int,
) -> tuple[Path, int, int]:
    """Собирает train/val в YOLO-раскладке. Возвращает (путь к data.yaml,
    число train, число val)."""
    for split in ("train", "val"):
        for kind in ("images", "labels"):
            target = out_dir / split / kind
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)

    items: list[tuple[Path, Path, dict[int, int]]] = []
    for directory, class_map in sources:
        items.extend((img, lbl, class_map) for img, lbl in _pairs(directory))

    random.Random(seed).shuffle(items)
    split_at = int(len(items) * (1 - val_share))

    counts = {"train": 0, "val": 0}
    for index, (image, label, class_map) in enumerate(items):
        split = "train" if index < split_at else "val"
        stem = f"{index:05d}"
        shutil.copy2(image, out_dir / split / "images" / f"{stem}{image.suffix.lower()}")
        remapped = _remap_label(label.read_text(encoding="utf-8"), class_map)
        (out_dir / split / "labels" / f"{stem}.txt").write_text(remapped, encoding="utf-8")
        counts[split] += 1

    data_yaml = out_dir / "data.yaml"
    data_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(out_dir.resolve()),
                "train": "train/images",
                "val": "val/images",
                "names": {i: name for i, name in enumerate(DETECTION_CLASSES)},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return data_yaml, counts["train"], counts["val"]


def _parse_class_map(raw: str | None) -> dict[int, int]:
    """`--class-map "0=excavator,1=dump_truck"` -> {0: idx(excavator), ...}."""
    if not raw:
        return {}
    mapping = {}
    for chunk in raw.split(","):
        source, target = chunk.split("=")
        name = target.strip()
        if name not in DETECTION_CLASSES:
            raise ValueError(
                f"класс {name!r} не входит в перечень docs/02 §3: {DETECTION_CLASSES}"
            )
        mapping[int(source)] = DETECTION_CLASSES.index(name)
    return mapping


def write_report(
    out_path: Path,
    *,
    metrics,
    n_train: int,
    n_val: int,
    weights: str,
    epochs: int,
    sources: list[str],
    note: str = "",
) -> None:
    """Отчёт по обучению — так же, как `docs/04-metrics.md`, заполняется
    только скриптом. Руками числа сюда не пишем (docs/01-principles.md, Definition of
    Done)."""
    per_class = []
    names = metrics.names if hasattr(metrics, "names") else {}
    for i, name in names.items():
        try:
            p, r, ap50, ap = metrics.box.class_result(i)
        except (IndexError, AttributeError):
            continue
        per_class.append(f"| {name} | {p:.3f} | {r:.3f} | {ap50:.3f} | {ap:.3f} |")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "\n".join(
            [
                "# Метрики детектора техники",
                "",
                "> Файл заполняется только скриптом `scripts/train_detector.py`.",
                "> Руками числа сюда не пишем.",
                "",
                f"Дата прогона: `{datetime.now().astimezone().isoformat(timespec='seconds')}`",
                f"Стартовые веса: `{weights}`, эпох: {epochs}.",
                f"Обучающих изображений: {n_train}, проверочных: {n_val}.",
                "",
                "Источники разметки:",
                *[f"- `{s}`" for s in sources],
                *(["", f"Происхождение набора: {note}"] if note else []),
                "",
                "## Сводно",
                "",
                "| Метрика | Значение | Цель |",
                "|---|---|---|",
                f"| mAP@50 | {metrics.box.map50:.3f} | ≥ 0.80 |",
                f"| mAP@50-95 | {metrics.box.map:.3f} | — |",
                f"| Precision | {metrics.box.mp:.3f} | — |",
                f"| Recall | {metrics.box.mr:.3f} | — |",
                "",
                "## По классам",
                "",
                "| Класс | Precision | Recall | mAP@50 | mAP@50-95 |",
                "|---|---|---|---|---|",
                *per_class,
                "",
                "> Метрики посчитаны на отложенной выборке того же набора, на",
                "> котором шло обучение. Это измеряет качество модели, но не её",
                "> переносимость на снимки с других площадок: собственный",
                "> проверочный набор с другой освещённостью, сезонностью и",
                "> ракурсами формируется отдельно (ТЗ, раздел 6.2).",
                "",
                "> Классы, отсутствующие в таблице по классам, детектором пока не",
                "> покрыты — для них нет размеченных примеров.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yolo-dir", type=Path, required=True, help="открытый набор YOLO")
    parser.add_argument(
        "--source-note",
        default="",
        help="откуда взят набор — попадает в отчёт как ссылка на источник",
    )
    parser.add_argument("--class-map", default="0=excavator", help="переназначение классов")
    parser.add_argument("--extra-dir", type=Path, help="своя разметка (те же классы, что у нас)")
    parser.add_argument("--out-dir", type=Path, default=Path("data/interim/det"))
    parser.add_argument("--weights", default="yolo11n.pt", help="стартовые веса")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="mps", help="mps / cpu / 0")
    parser.add_argument("--val-share", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--save-to", type=Path, default=Path("models/yolo11n_construction.pt")
    )
    parser.add_argument("--report", type=Path, default=Path("docs/04b-detector.md"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    sources = [(args.yolo_dir, _parse_class_map(args.class_map))]
    if args.extra_dir and args.extra_dir.exists():
        # Своя разметка уже в наших индексах — переназначать не нужно.
        sources.append((args.extra_dir, {i: i for i in range(len(DETECTION_CLASSES))}))

    data_yaml, n_train, n_val = build_dataset(
        sources, args.out_dir, val_share=args.val_share, seed=args.seed
    )
    print(f"датасет собран: train={n_train}, val={n_val} -> {data_yaml}")

    from ultralytics import YOLO

    model = YOLO(args.weights)
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        seed=args.seed,
        plots=True,
        verbose=True,
    )

    metrics = model.val(data=str(data_yaml), device=args.device)
    print(f"mAP@50    = {metrics.box.map50:.3f}")
    print(f"mAP@50-95 = {metrics.box.map:.3f}")

    write_report(
        args.report,
        metrics=metrics,
        n_train=n_train,
        n_val=n_val,
        weights=args.weights,
        epochs=args.epochs,
        sources=[d.name for d, _ in sources],
        note=args.source_note,
    )
    print(f"отчёт записан: {args.report}")

    args.save_to.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model.trainer.best, args.save_to)
    print(f"веса сохранены: {args.save_to}")


if __name__ == "__main__":
    main()
