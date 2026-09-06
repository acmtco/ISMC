"""Процедурная генерация спрайтов техники (без скачивания из сети).

Спрайты — не фотореалистичные вырезки, а простые геометрические иконки с
альфа-каналом, различимые по форме и цвету. Этого достаточно для
синтетического бенчмарка: он проверяет пайплайн (детекция -> машино-часы ->
отклонения), а не качество самого детектора.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from scripts.synth.classes import CLASS_COLORS, CLASS_INDEX, CLASS_SIZE
from scripts.synth.rng import rng_for

VARIANTS_PER_CLASS = 2


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def _draw_tracked_body(draw: ImageDraw.ImageDraw, x0, y0, x1, y1, color) -> None:
    draw.rectangle([x0, y0, x1, y1], fill=(*color, 255))
    tread = _darken(color, 0.5)
    draw.rectangle([x0, y1 - (y1 - y0) * 0.2, x1, y1], fill=(*tread, 255))


def _draw_wheeled_body(draw: ImageDraw.ImageDraw, x0, y0, x1, y1, color, rng) -> None:
    draw.rounded_rectangle([x0, y0, x1, y1], radius=4, fill=(*color, 255))
    wheel_r = (y1 - y0) * 0.22
    wheel_color = _darken(color, 0.3)
    for wx in (x0 + wheel_r, x1 - wheel_r):
        draw.ellipse(
            [wx - wheel_r, y1 - wheel_r * 0.6, wx + wheel_r, y1 + wheel_r * 1.4],
            fill=(*wheel_color, 255),
        )


def _draw_sprite(cls: str, seed: int) -> Image.Image:
    rng = rng_for(seed, CLASS_INDEX[cls])
    w, h = CLASS_SIZE[cls]
    pad = 6
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = CLASS_COLORS[cls]

    def jitter(base: int, spread: int) -> int:
        return max(0, min(255, base + rng.randint(-spread, spread)))

    color = (jitter(color[0], 12), jitter(color[1], 12), jitter(color[2], 12))
    x0, y0, x1, y1 = pad, pad, pad + w, pad + h
    cab_color = _darken(color, 0.7)

    if cls in ("excavator", "drilling_rig"):
        _draw_tracked_body(draw, x0, y0 + h * 0.45, x1, y1, color)
        draw.rectangle([x0 + w * 0.1, y0, x0 + w * 0.55, y0 + h * 0.5], fill=(*cab_color, 255))
        draw.line([x0 + w * 0.5, y0 + h * 0.2, x1, y0 + h * 0.05], fill=(*cab_color, 255), width=4)
    elif cls == "bulldozer":
        _draw_tracked_body(draw, x0, y0 + h * 0.4, x1, y1, color)
        draw.rectangle([x0 + w * 0.15, y0, x0 + w * 0.6, y0 + h * 0.45], fill=(*cab_color, 255))
        draw.rectangle([x0, y0 + h * 0.55, x0 + w * 0.12, y1], fill=(*cab_color, 255))
    elif cls in ("dump_truck", "concrete_mixer", "concrete_pump", "loader"):
        _draw_wheeled_body(draw, x0, y0 + h * 0.15, x1, y1 - h * 0.15, color, rng)
        draw.rectangle([x0, y0, x0 + w * 0.28, y0 + h * 0.5], fill=(*cab_color, 255))
        if cls == "concrete_mixer":
            drum_color = _darken(color, 1.15)
            draw.ellipse([x0 + w * 0.4, y0, x0 + w * 0.9, y0 + h * 0.75], fill=(*drum_color, 255))
    elif cls == "roller":
        _draw_wheeled_body(draw, x0, y0 + h * 0.2, x1, y1 - h * 0.15, color, rng)
        draw.ellipse([x0, y0 + h * 0.1, x0 + w * 0.35, y1], fill=(*_darken(color, 0.4), 255))
    elif cls == "tower_crane":
        mast_w = w * 0.18
        mast_box = [x0 + (w - mast_w) / 2, y0 + h * 0.1, x0 + (w + mast_w) / 2, y1]
        draw.rectangle(mast_box, fill=(*color, 255))
        draw.line([x0, y0 + h * 0.1, x1, y0 + h * 0.1], fill=(*cab_color, 255), width=5)
        base_box = [x0 + w * 0.3, y1 - h * 0.15, x1 - w * 0.3, y1]
        draw.rectangle(base_box, fill=(*_darken(color, 0.5), 255))
    elif cls == "mobile_crane":
        _draw_wheeled_body(draw, x0, y0 + h * 0.45, x0 + w * 0.55, y1 - h * 0.1, color, rng)
        draw.line([x0 + w * 0.35, y0 + h * 0.5, x1, y0], fill=(*cab_color, 255), width=5)
    else:  # pragma: no cover - защитная ветка на случай нового класса
        draw.rectangle([x0, y0, x1, y1], fill=(*color, 255))

    return img


def ensure_sprites(sprites_dir: Path, seed: int, classes: list[str]) -> dict[str, list[Path]]:
    """Гарантирует наличие спрайтов на диске, генерируя недостающие.

    Детерминировано по `seed`: одинаковый seed -> одинаковые PNG-байты.
    """
    result: dict[str, list[Path]] = {}
    for cls in classes:
        cls_dir = sprites_dir / cls
        cls_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for variant in range(VARIANTS_PER_CLASS):
            path = cls_dir / f"sprite_{variant:02d}.png"
            if not path.exists():
                sprite_seed = seed * 1000 + CLASS_INDEX[cls] * 10 + variant
                _draw_sprite(cls, sprite_seed).save(path)
            paths.append(path)
        result[cls] = paths
    return result
