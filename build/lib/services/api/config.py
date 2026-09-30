"""Пути и конфиги API — разрешаются из переменных окружения (`.env.example`).

Без кэширования: файлы маленькие (YAML/JSON-справочники), а тесты меняют
`HG_DATA_DIR`/`HG_CONFIG_DIR` через переменные окружения между прогонами —
кэш только мешал бы.
"""
from __future__ import annotations

import os
from pathlib import Path

from services.analytics.deviations import DeviationEngine
from services.analytics.economics import CostReference
from services.analytics.forecast import ForecastConfig, SpiThresholds
from services.analytics.schedule_io import ProductivityRef


def data_dir() -> Path:
    return Path(os.environ.get("HG_DATA_DIR", "./data"))


def config_dir() -> Path:
    return Path(os.environ.get("HG_CONFIG_DIR", "./config"))


def ref_dir() -> Path:
    return data_dir() / "ref"


def objects_json_path() -> Path:
    return ref_dir() / "objects.json"


def models_dir() -> Path:
    return data_dir().parent / "models"


def object_id_default() -> str:
    return os.environ.get("HG_OBJECT_ID", "OBJ-001")


def replay_speed_default() -> float:
    return float(os.environ.get("HG_REPLAY_SPEED", "60"))


def detections_path(camera_id: str) -> Path:
    """Куда `IncrementalPipeline`/планировщик пишут поток детекций камеры."""
    return data_dir() / "interim" / "detections" / f"{camera_id}.jsonl"


def forecast_config() -> ForecastConfig:
    return ForecastConfig.from_yaml(config_dir() / "thresholds.yaml")


def spi_thresholds() -> SpiThresholds:
    return SpiThresholds.from_yaml(config_dir() / "thresholds.yaml")


def cost_reference() -> CostReference:
    return CostReference.from_json(ref_dir() / "machine_hour_cost.json")


def productivity_ref() -> ProductivityRef:
    return ProductivityRef.from_json(ref_dir() / "productivity.json")


def deviation_engine() -> DeviationEngine:
    return DeviationEngine.load(
        work_signatures_path=ref_dir() / "work_signatures.json",
        matching_config_path=config_dir() / "matching.yaml",
        thresholds_path=config_dir() / "thresholds.yaml",
        machine_hour_cost_path=ref_dir() / "machine_hour_cost.json",
    )
