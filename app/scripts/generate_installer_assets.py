from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PIL import Image, ImageDraw, ImageFilter, ImageFont

Size = tuple[int, int]
Bounds = tuple[int, int, int, int]


@dataclass(frozen=True)
class BackdropTheme:
    base_top: tuple[int, int, int]
    base_bottom: tuple[int, int, int]
    accent_a_color: tuple[int, int, int]
    accent_a_strength: int
    accent_b_color: tuple[int, int, int]
    accent_b_strength: int
    panel_fill: tuple[int, int, int, int]
    panel_stroke: tuple[int, int, int, int]


def _backdrop_theme(dark: bool) -> BackdropTheme:
    if dark:
        return BackdropTheme(
            base_top=(8, 14, 30),
            base_bottom=(4, 8, 18),
            accent_a_color=(46, 112, 255),
            accent_a_strength=128,
            accent_b_color=(0, 196, 255),
            accent_b_strength=88,
            panel_fill=(9, 16, 30, 42),
            panel_stroke=(255, 255, 255, 18),
        )

    return BackdropTheme(
        base_top=(246, 249, 255),
        base_bottom=(231, 238, 250),
        accent_a_color=(72, 129, 255),
        accent_a_strength=76,
        accent_b_color=(103, 211, 255),
        accent_b_strength=52,
        panel_fill=(255, 255, 255, 84),
        panel_stroke=(114, 144, 196, 28),
    )


def _ensure_rgba(image: Image.Image, size: Size) -> Image.Image:
    return image.convert("RGBA").resize(size, Image.Resampling.LANCZOS)


def _load_font(size: int, *, bold: bool) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    font_names = (
        ["DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["DejaVuSans.ttf", "Arial.ttf"]
    )
    for name in font_names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _radial_glow(size: Size, color: tuple[int, int, int], strength: int) -> Image.Image:
    width, height = size
    cx = width / 2
    cy = height / 2
    rx = max(1.0, width / 2)
    ry = max(1.0, height / 2)
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(height):
        dy = (y - cy) / ry
        for x in range(width):
            dx = (x - cx) / rx
            raw_dist = float(math.sqrt(float(dx * dx + dy * dy)))
            dist = 1.0 if raw_dist > 1.0 else raw_dist
            distance_factor = 1.0 - dist
            alpha_value = distance_factor * distance_factor * math.sqrt(distance_factor) * strength
            alpha = int(alpha_value)
            pixels.append((*color, alpha))
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow.putdata(pixels)
    blur_radius = max(10, min(width, height) // 20)
    return glow.filter(ImageFilter.GaussianBlur(blur_radius))


def _vertical_gradient(
    size: Size, top: tuple[int, int, int], bottom: tuple[int, int, int]
) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] * (1.0 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, width, y), fill=(*color, 255))
    return image


def _build_backdrop(size: Size, dark: bool) -> Image.Image:
    theme = _backdrop_theme(dark)
    base = _vertical_gradient(size, theme.base_top, theme.base_bottom)
    accent_a = _radial_glow(
        (size[0] * 2 // 3, size[1] * 2 // 3), theme.accent_a_color, theme.accent_a_strength
    )
    accent_b = _radial_glow(
        (size[0] // 2, size[1] // 2), theme.accent_b_color, theme.accent_b_strength
    )

    canvas = base
    canvas.alpha_composite(accent_a, (int(size[0] * -0.08), int(size[1] * -0.1)))
    canvas.alpha_composite(accent_b, (int(size[0] * 0.62), int(size[1] * 0.34)))

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (int(size[0] * 0.08), int(size[1] * 0.12), int(size[0] * 0.92), int(size[1] * 0.88)),
        radius=int(min(size) * 0.08),
        fill=theme.panel_fill,
        outline=theme.panel_stroke,
        width=max(1, min(size) // 220),
    )
    return canvas


def _paste_logo_card(canvas: Image.Image, logo: Image.Image, bounds: Bounds, dark: bool) -> None:
    left, top, right, bottom = bounds
    card = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    card_width, card_height = card.size
    radius = max(18, min(card_width, card_height) // 8)

    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (0, 0, card_width - 1, card_height - 1),
        radius=radius,
        fill=(10, 16, 28, 214) if dark else (255, 255, 255, 222),
        outline=(255, 255, 255, 36) if dark else (125, 151, 199, 48),
        width=max(1, min(card_width, card_height) // 48),
    )

    shadow = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (12, 18, card_width - 12, card_height - 6),
        radius=radius,
        fill=(0, 0, 0, 68 if dark else 28),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(6, min(card_width, card_height) // 16)))
    canvas.alpha_composite(shadow, (left, top))
    canvas.alpha_composite(card, (left, top))

    inset = max(18, min(card_width, card_height) // 9)
    logo_size = min(card_width, card_height) - inset * 2
    logo_resized = _ensure_rgba(logo, (logo_size, logo_size))
    logo_left = left + (card_width - logo_size) // 2
    logo_top = top + (card_height - logo_size) // 2
    canvas.alpha_composite(logo_resized, (logo_left, logo_top))


def _draw_text_block(
    canvas: Image.Image,
    title: str,
    subtitle: str,
    anchor: tuple[int, int],
    dark: bool,
    *,
    title_size: int,
    subtitle_size: int,
) -> None:
    draw = ImageDraw.Draw(canvas)
    title_color = (244, 248, 255, 255) if dark else (14, 23, 43, 255)
    body_color = (203, 214, 234, 255) if dark else (84, 103, 131, 255)
    title_font = _load_font(title_size, bold=True)
    body_font = _load_font(subtitle_size, bold=False)

    draw.text(anchor, title, fill=title_color, font=title_font)
    title_box = draw.textbbox(anchor, title, font=title_font)
    subtitle_y = title_box[3] + max(10, subtitle_size // 2)
    draw.multiline_text(
        (anchor[0], subtitle_y),
        subtitle,
        fill=body_color,
        font=body_font,
        spacing=max(6, subtitle_size // 3),
    )


def build_wizard_panel(logo: Image.Image, output: Path, dark: bool) -> None:
    size = (404, 772)
    canvas = _build_backdrop(size, dark)
    _paste_logo_card(canvas, logo, (56, 82, 348, 374), dark)
    _draw_text_block(
        canvas,
        "Bao",
        "Personal AI assistant\nthat remembers, learns,\nand evolves.",
        (58, 446),
        dark,
        title_size=58,
        subtitle_size=24,
    )
    canvas.save(output, format="PNG")


def build_wizard_small(logo: Image.Image, output: Path, dark: bool) -> None:
    size = (128, 128)
    canvas = _build_backdrop(size, dark)
    _paste_logo_card(canvas, logo, (18, 18, 110, 110), dark)
    canvas.save(output, format="PNG")


def build_wizard_back(logo: Image.Image, output: Path, dark: bool) -> None:
    size = (1194, 864)
    canvas = _build_backdrop(size, dark)
    _paste_logo_card(canvas, logo, (764, 136, 1036, 408), dark)
    _draw_text_block(
        canvas,
        "Bao Desktop",
        "A focused Windows setup experience\nfor your AI workspace.",
        (108, 154),
        dark,
        title_size=56,
        subtitle_size=24,
    )

    draw = ImageDraw.Draw(canvas)
    line_color = (255, 255, 255, 28) if dark else (33, 99, 204, 34)
    draw.rounded_rectangle(
        (108, 534, 478, 642),
        radius=28,
        outline=line_color,
        width=2,
    )
    draw.multiline_text(
        (144, 566),
        "Desktop chat, memory, and gateway tools\nready in one install.",
        fill=(214, 224, 239, 255) if dark else (70, 92, 122, 255),
        font=_load_font(22, bold=False),
        spacing=8,
    )
    canvas.save(output, format="PNG")


def _build_all_assets(logo: Image.Image, output_dir: Path) -> list[Path]:
    generated_paths = [
        output_dir / "wizard-image-light.png",
        output_dir / "wizard-image-dark.png",
        output_dir / "wizard-small-light.png",
        output_dir / "wizard-small-dark.png",
        output_dir / "wizard-back-light.png",
        output_dir / "wizard-back-dark.png",
    ]
    build_wizard_panel(logo, generated_paths[0], dark=False)
    build_wizard_panel(logo, generated_paths[1], dark=True)
    build_wizard_small(logo, generated_paths[2], dark=False)
    build_wizard_small(logo, generated_paths[3], dark=True)
    build_wizard_back(logo, generated_paths[4], dark=False)
    build_wizard_back(logo, generated_paths[5], dark=True)
    return generated_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate branded Windows installer assets")
    _ = parser.add_argument(
        "--source",
        default="app/resources/logo-circle.png",
        help="Source logo path (default: app/resources/logo-circle.png)",
    )
    _ = parser.add_argument(
        "--output-dir",
        default="app/resources/installer",
        help="Output directory for installer PNG assets",
    )
    args = parser.parse_args()

    source = Path(cast(str, args.source)).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source logo not found: {source}")
    output_dir = Path(cast(str, args.output_dir)).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as raw_logo:
        logo = raw_logo.convert("RGBA")
    generated_paths = _build_all_assets(logo, output_dir)

    print(f"Generated installer assets in {output_dir}")
    for path in generated_paths:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
