"""Освещённость по времени суток, погода, качество кадра.

Честность важнее красивых цифр (docs/01-principles.md, правило 4): чем хуже кадр
(ночь, дождь/туман, перекрытие), тем ниже `quality.score` — так же, как
должна вести себя `services/perception` на реальных кадрах.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from scripts.synth.scenario import Scenario


def is_night(scenario: Scenario, hour: int) -> bool:
    return hour < scenario.day_start_hour or hour >= scenario.day_end_hour


def brightness_factor(scenario: Scenario, hour: int, minute: int) -> float:
    if is_night(scenario, hour):
        return 0.28
    span = max(scenario.day_end_hour - scenario.day_start_hour, 1)
    t = (hour + minute / 60 - scenario.day_start_hour) / span
    t = min(max(t, 0.0), 1.0)
    return 0.78 + 0.32 * math.sin(math.pi * t)


def apply_lighting(img: Image.Image, scenario: Scenario, hour: int, minute: int) -> Image.Image:
    factor = brightness_factor(scenario, hour, minute)
    out = ImageEnhance.Brightness(img).enhance(factor)
    if is_night(scenario, hour):
        out = ImageEnhance.Color(out).enhance(0.6)
    return out


def apply_weather(img: Image.Image, condition: str | None, rng: random.Random) -> Image.Image:
    if condition == "rain":
        out = ImageEnhance.Color(img).enhance(0.75)
        out = ImageEnhance.Brightness(out).enhance(0.85)
        out = out.convert("RGBA")
        overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        w, h = out.size
        for _ in range(int(w * h / 6000)):
            x = rng.randint(0, w)
            y = rng.randint(0, h)
            length = rng.randint(6, 14)
            draw.line([x, y, x - length // 3, y + length], fill=(210, 220, 230, 60), width=1)
        return Image.alpha_composite(out, overlay).convert("RGB")
    if condition == "fog":
        out = img.filter(ImageFilter.GaussianBlur(radius=2.5))
        overlay = Image.new("RGB", out.size, (225, 228, 230))
        return Image.blend(out, overlay, alpha=0.4)
    return img


def compute_quality(
    *, night: bool, weather_condition: str | None, occlusion_fraction: float, rng: random.Random
) -> dict:
    score = 1.0
    blur = 0.05 + rng.random() * 0.05
    if night:
        score -= 0.5
        blur += 0.15
    if weather_condition == "rain":
        score -= 0.3
        blur += 0.10
    elif weather_condition == "fog":
        score -= 0.35
        blur += 0.20
    score -= occlusion_fraction * 0.6
    return {
        "blur": round(min(max(blur, 0.0), 1.0), 2),
        "night": night,
        "occlusion": round(min(max(occlusion_fraction, 0.0), 1.0), 2),
        "score": round(min(max(score, 0.0), 1.0), 2),
    }
