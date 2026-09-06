"""Общие фикстуры для тестов services/api.

`HG_DB_URL` кэшируется в `services.api.db._engine` — для изоляции тестов
сбрасываем кэш до и после каждого прогона.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REF_FILES = ["work_signatures.json", "productivity.json", "machine_hour_cost.json", "objects.json"]


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    """Изолированные `HG_DATA_DIR`/`HG_DB_URL`; `HG_CONFIG_DIR` — настоящий
    конфиг проекта (статичен, общий для всех тестов)."""
    data_dir = tmp_path / "data"
    ref_dir = data_dir / "ref"
    ref_dir.mkdir(parents=True)
    for name in REF_FILES:
        shutil.copy(Path("data/ref") / name, ref_dir / name)

    monkeypatch.setenv("HG_DATA_DIR", str(data_dir))
    monkeypatch.setenv("HG_DB_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("HG_CONFIG_DIR", "config")

    from services.api.db import reset_engine_cache

    reset_engine_cache()
    yield data_dir
    reset_engine_cache()
