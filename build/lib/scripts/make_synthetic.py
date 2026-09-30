"""Генерация синтетического бенчмарка стройплощадки методом композитинга.

Собирает кадры из процедурного фона + процедурных спрайтов техники (никаких
скачиваний из сети), применяет освещённость по времени суток, погоду
(дождь/туман), ночные кадры и случайные частичные перекрытия — и пишет
честный ground truth рядом, по контракту `docs/02-data-contract.md`.

Вход — сценарий YAML (см. `data/ref/scenario_demo.yaml`): 30 суток строительства,
какие работы идут в каких зонах, состав техники, и `injected_deviations` —
список внедрённых отклонений (R1-R4) с точными датами и параметрами.

Выход:
  data/synthetic/<camera_id>/<YYYYMMDDTHHMMSS>.jpg  — кадры
  data/benchmark/ground_truth.jsonl                 — истинная разметка (детекции)
  data/benchmark/expected_deviations.jsonl          — истинные отклонения

Детерминировано по --seed: одинаковый seed -> побитово одинаковые кадры и JSONL.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from scripts.synth.background import generate_background
from scripts.synth.classes import CLASSES
from scripts.synth.compose import compose_frame
from scripts.synth.io_utils import progress, write_jsonl
from scripts.synth.scenario import Scenario, load_scenario
from scripts.synth.schedule import effective_works_for_day
from scripts.synth.sprites import ensure_sprites
from scripts.synth.timegrid import frame_times
from scripts.synth.tracks import TrackRegistry

MSK = timezone(timedelta(hours=3))


def _load_sprites(sprites_dir: Path, seed: int) -> dict[str, list[Image.Image]]:
    paths = ensure_sprites(sprites_dir, seed, CLASSES)
    return {
        cls: [Image.open(p).convert("RGBA") for p in cls_paths] for cls, cls_paths in paths.items()
    }


def _expected_deviations(scenario: Scenario, first_day: date, last_day: date) -> list[dict]:
    records = []
    for dev in scenario.injected_deviations:
        if dev.date_to < first_day or dev.date_from > last_day:
            continue
        records.append(
            {
                "deviation_id": dev.deviation_id,
                "type": dev.type,
                "work_id": dev.work_id,
                "zone_id": dev.zone_id,
                "period": {"from": dev.date_from.isoformat(), "to": dev.date_to.isoformat()},
                "severity": dev.severity,
                "params": dev.params,
            }
        )
    return records


def generate(
    scenario: Scenario, days: int, sprites_dir: Path, out_dir: Path, benchmark_dir: Path
) -> int:
    sprites = _load_sprites(sprites_dir, scenario.seed)
    background = generate_background(scenario.frame_size, scenario.zones, scenario.seed)

    frames_dir = out_dir / scenario.camera_id
    frames_dir.mkdir(parents=True, exist_ok=True)
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    times = frame_times(scenario)
    total = days * len(times)
    track_registry = TrackRegistry()

    gt_path = benchmark_dir / "ground_truth.jsonl"
    frame_count = 0
    with gt_path.open("w", encoding="utf-8") as gt_file:
        bar = progress(range(total), total=total, desc="синтетика")
        for day_index in range(days):
            day = scenario.start_date + timedelta(days=day_index)
            works = effective_works_for_day(scenario, day)

            for frame_index, (hour, minute) in enumerate(times):
                img, objects, quality = compose_frame(
                    scenario=scenario,
                    background=background,
                    sprites=sprites,
                    works=works,
                    day=day,
                    day_index=day_index,
                    hour=hour,
                    minute=minute,
                    frame_index=frame_index,
                    track_registry=track_registry,
                )

                ts = datetime(day.year, day.month, day.day, hour, minute, tzinfo=MSK)
                frame_name = ts.strftime("%Y%m%dT%H%M%S") + ".jpg"
                frame_path = frames_dir / frame_name
                img.save(frame_path, format="JPEG", quality=90)

                record = {
                    "camera_id": scenario.camera_id,
                    "ts": ts.isoformat(),
                    "frame_uri": frame_path.as_posix(),
                    "quality": quality,
                    "objects": objects,
                }
                gt_file.write(json.dumps(record, ensure_ascii=False))
                gt_file.write("\n")

                frame_count += 1
                bar.update(1)
        bar.close()

    last_day = scenario.start_date + timedelta(days=days - 1)
    write_jsonl(
        benchmark_dir / "expected_deviations.jsonl",
        _expected_deviations(scenario, scenario.start_date, last_day),
    )

    return frame_count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--scenario", type=Path, default=Path("data/ref/scenario_demo.yaml"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--benchmark-dir", type=Path, default=Path("data/benchmark"))
    parser.add_argument("--sprites-dir", type=Path, default=Path("data/ref/sprites"))
    parser.add_argument("--seed", type=int, default=None, help="переопределить seed из сценария")
    parser.add_argument(
        "--days", type=int, default=None, help="переопределить число суток из сценария"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    scenario = load_scenario(args.scenario)
    if args.seed is not None:
        scenario = replace(scenario, seed=args.seed)
    days = args.days if args.days is not None else scenario.days
    if days < 1:
        raise SystemExit("--days должен быть >= 1")

    frame_count = generate(scenario, days, args.sprites_dir, args.out_dir, args.benchmark_dir)

    print(f"Сгенерировано кадров: {frame_count}")
    print(f"Ground truth: {args.benchmark_dir / 'ground_truth.jsonl'}")
    print(f"Ожидаемые отклонения: {args.benchmark_dir / 'expected_deviations.jsonl'}")


if __name__ == "__main__":
    main()
