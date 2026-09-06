"""Композитинг одного кадра: фон + спрайты + освещение + погода + перекрытие.

Возвращает изображение и ground truth по контракту `detections.jsonl`
(docs/02-data-contract.md, раздел 3) — только с `conf` / `state_conf` = 1.0,
потому что это истинная разметка, а не выход детектора.
"""
from __future__ import annotations

import random
from datetime import date

from PIL import Image, ImageDraw

from scripts.synth import effects, layout
from scripts.synth.classes import CLASS_INDEX
from scripts.synth.rng import rng_for
from scripts.synth.scenario import Scenario
from scripts.synth.schedule import EffectiveWork
from scripts.synth.tracks import TrackRegistry

OCCLUSION_PROBABILITY = 0.08

_STATE_JITTER = {"active": 6.0, "idle": 2.0, "parked": 0.0}
_STATE_FEATURES = {
    "active": {
        "centroid_mad": (3.0, 7.0),
        "area_mad": (150.0, 400.0),
        "flow_mag": (1.2, 2.5),
        "hsv_var": (300.0, 900.0),
    },
    "idle": {
        "centroid_mad": (0.5, 2.0),
        "area_mad": (10.0, 60.0),
        "flow_mag": (0.1, 0.6),
        "hsv_var": (80.0, 300.0),
    },
    "parked": {
        "centroid_mad": (0.0, 0.3),
        "area_mad": (0.0, 5.0),
        "flow_mag": (0.0, 0.05),
        "hsv_var": (0.0, 80.0),
    },
}


def _sample(rng: random.Random, bounds: tuple[float, float]) -> float:
    lo, hi = bounds
    return round(lo + rng.random() * (hi - lo), 2)


def _unit_state(
    *,
    seed: int,
    day_index: int,
    frame_index: int,
    zone_index: int,
    cls_index: int,
    unit_index: int,
    active_ratio: float,
    work_active_hour: bool,
    night: bool,
) -> str:
    if night or not work_active_hour:
        return "parked"
    rng = rng_for(seed, day_index, frame_index, zone_index, cls_index, unit_index, 2)
    return "active" if rng.random() < active_ratio else "idle"


def compose_frame(
    *,
    scenario: Scenario,
    background: Image.Image,
    sprites: dict[str, list[Image.Image]],
    works: list[EffectiveWork],
    day: date,
    day_index: int,
    hour: int,
    minute: int,
    frame_index: int,
    track_registry: TrackRegistry,
) -> tuple[Image.Image, list[dict], dict]:
    zone_index_of = {z.zone_id: i for i, z in enumerate(scenario.zones)}
    night = effects.is_night(scenario, hour)
    weather_condition = scenario.weather_on(day)
    frame_rng = rng_for(scenario.seed, day_index, frame_index, 999)

    img = background.copy()
    objects: list[dict] = []
    candidate_boxes: list[tuple[int, int, int, int]] = []

    for work in sorted(works, key=lambda w: w.work_id):
        zone_index = zone_index_of[work.zone_id]
        zone_bbox = scenario.zone(work.zone_id).bbox()
        work_active_hour = (not night) and any(
            start <= hour < end for start, end in work.active_hours
        )

        for cls in sorted(work.classes):
            spec = work.classes[cls]
            cls_index = CLASS_INDEX[cls]
            variants = sprites[cls]

            for unit_index in range(spec.count):
                state = _unit_state(
                    seed=scenario.seed,
                    day_index=day_index,
                    frame_index=frame_index,
                    zone_index=zone_index,
                    cls_index=cls_index,
                    unit_index=unit_index,
                    active_ratio=spec.active_ratio,
                    work_active_hour=work_active_hour,
                    night=night,
                )

                style_rng = rng_for(scenario.seed, zone_index, cls_index, unit_index, 1)
                scale = 0.85 + style_rng.random() * 0.3
                sprite = variants[unit_index % len(variants)]

                ax, ay = layout.unit_anchor(
                    scenario.seed, zone_index, zone_bbox, cls_index, unit_index
                )
                jx, jy = layout.frame_jitter(
                    scenario.seed,
                    day_index,
                    frame_index,
                    zone_index,
                    cls_index,
                    unit_index,
                    _STATE_JITTER[state],
                )
                cx, cy = ax + jx, ay + jy

                sw, sh = int(sprite.width * scale), int(sprite.height * scale)
                sprite_resized = sprite.resize((max(sw, 1), max(sh, 1)))
                # (cx, cy) — точка опоры (низ бокса по центру), не центр бокса:
                # так же, как assign_zone определяет принадлежность зоне
                # (services/perception/zones.py) — иначе высокая техника
                # (башенный кран) считалась бы вне зоны по своему же ground truth.
                x0, y0 = int(cx - sw / 2), int(cy - sh)
                img.paste(sprite_resized, (x0, y0), sprite_resized)

                feat_rng = rng_for(
                    scenario.seed, day_index, frame_index, zone_index, cls_index, unit_index, 3
                )
                bounds = _STATE_FEATURES[state]
                features = {
                    "centroid_mad": _sample(feat_rng, bounds["centroid_mad"]),
                    "area_mad": _sample(feat_rng, bounds["area_mad"]),
                    "flow_mag": _sample(feat_rng, bounds["flow_mag"]),
                    "hsv_var": _sample(feat_rng, bounds["hsv_var"]),
                }

                bbox = [x0, y0, sw, sh]
                track_id = track_registry.get(work.zone_id, cls, unit_index)
                objects.append(
                    {
                        "track_id": track_id,
                        "cls": cls,
                        "conf": 1.0,
                        "bbox": bbox,
                        "zone_id": work.zone_id,
                        "state": state,
                        "state_conf": 1.0,
                        "features": features,
                    }
                )
                candidate_boxes.append((x0, y0, sw, sh))

    img = effects.apply_lighting(img.convert("RGB"), scenario, hour, minute)
    img = effects.apply_weather(img, weather_condition, frame_rng)

    occlusion_fraction = 0.0
    if candidate_boxes and frame_rng.random() < OCCLUSION_PROBABILITY:
        bx, by, bw, bh = frame_rng.choice(candidate_boxes)
        ox0, oy0 = bx, by + int(bh * 0.4)
        ox1, oy1 = bx + bw, by + bh
        draw = ImageDraw.Draw(img, "RGBA")
        draw.rectangle([ox0, oy0, ox1, oy1], fill=(40, 40, 40, 160))
        frame_area = scenario.frame_size[0] * scenario.frame_size[1]
        occlusion_fraction = ((ox1 - ox0) * (oy1 - oy0)) / frame_area

    quality = effects.compute_quality(
        night=night,
        weather_condition=weather_condition,
        occlusion_fraction=occlusion_fraction,
        rng=frame_rng,
    )

    return img, objects, quality
