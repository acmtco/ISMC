"""Запись JSONL и обёртка прогресс-бара."""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from tqdm import tqdm


def write_jsonl(path: Path, records: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")
            count += 1
    return count


def progress(iterable, total: int, desc: str):
    return tqdm(iterable, total=total, desc=desc, unit="кадр")
