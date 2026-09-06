"""Принадлежность бокса зоне (`objects.json[*].cameras[*].zones`, docs/02 §1).

Точка привязки — центр нижней грани бокса (точка касания земли), а не
центр бокса: для техники с высокой надстройкой (башенный кран, экскаватор
с поднятой стрелой) центр бокса может оказаться за пределами зоны, а точка
опоры — всегда там, где стоит техника.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Zone:
    zone_id: str
    polygon: list[tuple[float, float]]


def ground_point(bbox: list[float]) -> tuple[float, float]:
    x, y, w, h = bbox
    return x + w / 2, y + h


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Ray casting — стандартный алгоритм "точка в многоугольнике"."""
    x, y = point
    inside = False
    n = len(polygon)
    x1, y1 = polygon[-1]
    for i in range(n):
        x2, y2 = polygon[i]
        crosses = (y1 > y) != (y2 > y)
        if crosses:
            x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_intersect:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def assign_zone(bbox: list[float], zones: list[Zone]) -> str | None:
    point = ground_point(bbox)
    for zone in zones:
        if point_in_polygon(point, zone.polygon):
            return zone.zone_id
    return None


def load_zones(objects_json_path: Path, camera_id: str) -> list[Zone]:
    """Зоны конкретной камеры из `objects.json` (docs/02, раздел 1)."""
    data = json.loads(Path(objects_json_path).read_text(encoding="utf-8"))
    for camera in data.get("cameras", []):
        if camera["camera_id"] == camera_id:
            return [
                Zone(zone_id=z["zone_id"], polygon=[tuple(p) for p in z["polygon"]])
                for z in camera.get("zones", [])
            ]
    raise ValueError(f"камера {camera_id!r} не найдена в {objects_json_path}")
