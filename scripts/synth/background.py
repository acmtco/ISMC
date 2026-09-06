"""Процедурная фоновая фотография площадки (без скачивания из сети)."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from scripts.synth.scenario import Zone


def _noise_layer(
    size: tuple[int, int], rng: np.random.Generator, base: int, spread: int
) -> np.ndarray:
    return rng.integers(base - spread, base + spread + 1, size=(size[1], size[0]), endpoint=True)


def generate_background(frame_size: tuple[int, int], zones: list[Zone], seed: int) -> Image.Image:
    w, h = frame_size
    rng = np.random.default_rng(seed)
    horizon = int(h * 0.35)

    img = Image.new("RGB", (w, h))
    arr = np.zeros((h, w, 3), dtype=np.uint8)

    # небо: вертикальный градиент + лёгкий шум
    sky_top = np.array([176, 205, 226])
    sky_bottom = np.array([214, 227, 236])
    for y in range(horizon):
        t = y / max(horizon - 1, 1)
        arr[y, :, :] = (sky_top * (1 - t) + sky_bottom * t).astype(np.uint8)

    # грунт: коричнево-серый шум
    ground_noise = _noise_layer((w, h - horizon), rng, base=0, spread=10)
    ground_base = np.array([148, 138, 122])
    ground = np.clip(ground_base + ground_noise[..., None], 0, 255).astype(np.uint8)
    arr[horizon:, :, :] = ground

    img = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    for zone in zones:
        draw.polygon(zone.polygon, fill=(96, 80, 60, 90), outline=(255, 210, 60, 200))

    # статичный "мусор" площадки: кучи, ограждение — для визуальной достоверности
    for _ in range(6):
        cx = rng.integers(0, w)
        cy = rng.integers(horizon, h)
        r = rng.integers(8, 22)
        shade = int(rng.integers(90, 140))
        draw.ellipse(
            [cx - r, cy - r * 0.5, cx + r, cy + r * 0.5],
            fill=(shade, shade - 10, shade - 25, 255),
        )

    fence_y = horizon - 4
    draw.line([(0, fence_y), (w, fence_y)], fill=(120, 120, 120, 160), width=2)

    return img.convert("RGB")
