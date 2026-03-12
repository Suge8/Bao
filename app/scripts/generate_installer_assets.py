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
class BrandTheme:
    base_top: tuple[int, int, int]
    base_bottom: tuple[int, int, int]
    accent_main: tuple[int, int, int]
    accent_secondary: tuple[int, int, int]
    accent_main_strength: int
    accent_secondary_strength: int
    panel_fill: tuple[int, int, int, int]
    panel_stroke: tuple[int, int, int, int]
    card_fill: tuple[int, int, int, int]
    card_stroke: tuple[int, int, int, int]
    text_primary: tuple[int, int, int, int]
    text_secondary: tuple[int, int, int, int]
    pill_fill: tuple[int, int, int, int]
    pill_text: tuple[int, int, int, int]
    arrow_line: tuple[int, int, int, int]
    arrow_glow: tuple[int, int, int, int]


def _theme(dark: bool) -> BrandTheme:
    if dark:
        return BrandTheme(
            base_top=(19, 14, 11),
            base_bottom=(11, 8, 6),
            accent_main=(255, 179, 61),
            accent_secondary=(198, 134, 66),
            accent_main_strength=112,
            accent_secondary_strength=74,
            panel_fill=(28, 20, 15, 210),
            panel_stroke=(255, 222, 181, 26),
            card_fill=(38, 28, 22, 226),
            card_stroke=(255, 210, 150, 32),
            text_primary=(247, 239, 231, 255),
            text_secondary=(197, 175, 158, 255),
            pill_fill=(255, 179, 61, 255),
            pill_text=(30, 20, 14, 255),
            arrow_line=(255, 200, 134, 126),
            arrow_glow=(255, 179, 61, 62),
        )

    return BrandTheme(
        base_top=(252, 248, 244),
        base_bottom=(243, 236, 230),
        accent_main=(255, 179, 61),
        accent_secondary=(198, 134, 66),
        accent_main_strength=72,
        accent_secondary_strength=48,
        panel_fill=(255, 252, 248, 224),
        panel_stroke=(182, 142, 104, 28),
        card_fill=(255, 255, 255, 236),
        card_stroke=(201, 170, 138, 40),
        text_primary=(38, 26, 18, 255),
        text_secondary=(107, 86, 73, 255),
        pill_fill=(255, 179, 61, 255),
        pill_text=(30, 20, 14, 255),
        arrow_line=(194, 136, 66, 118),
        arrow_glow=(255, 179, 61, 46),
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
            raw_dist = math.sqrt(dx * dx + dy * dy)
            dist = 1.0 if raw_dist > 1.0 else raw_dist
            distance_factor = 1.0 - dist
            alpha = int(distance_factor * distance_factor * math.sqrt(distance_factor) * strength)
            pixels.append((*color, alpha))
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow.putdata(pixels)
    blur_radius = max(10, min(width, height) // 18)
    return glow.filter(ImageFilter.GaussianBlur(blur_radius))


def _build_backdrop(size: Size, dark: bool) -> Image.Image:
    theme = _theme(dark)
    canvas = _vertical_gradient(size, theme.base_top, theme.base_bottom)
    accent_a = _radial_glow(
        (size[0] * 2 // 3, size[1] * 2 // 3), theme.accent_main, theme.accent_main_strength
    )
    accent_b = _radial_glow(
        (size[0] // 2, size[1] // 2), theme.accent_secondary, theme.accent_secondary_strength
    )
    canvas.alpha_composite(accent_a, (int(size[0] * -0.06), int(size[1] * -0.12)))
    canvas.alpha_composite(accent_b, (int(size[0] * 0.58), int(size[1] * 0.24)))
    return canvas


def _rounded_panel(canvas: Image.Image, bounds: Bounds, *, dark: bool) -> None:
    left, top, right, bottom = bounds
    theme = _theme(dark)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        bounds,
        radius=max(18, min(right - left, bottom - top) // 10),
        fill=theme.panel_fill,
        outline=theme.panel_stroke,
        width=max(1, min(right - left, bottom - top) // 180),
    )


def _paste_logo_card(canvas: Image.Image, logo: Image.Image, bounds: Bounds, *, dark: bool) -> None:
    left, top, right, bottom = bounds
    theme = _theme(dark)
    card = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    card_width, card_height = card.size
    radius = max(18, min(card_width, card_height) // 8)

    shadow = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (14, 18, card_width - 14, card_height - 6),
        radius=radius,
        fill=(0, 0, 0, 72 if dark else 24),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(8, min(card_width, card_height) // 14)))
    canvas.alpha_composite(shadow, (left, top))

    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (0, 0, card_width - 1, card_height - 1),
        radius=radius,
        fill=theme.card_fill,
        outline=theme.card_stroke,
        width=max(1, min(card_width, card_height) // 48),
    )
    canvas.alpha_composite(card, (left, top))

    inset = max(18, min(card_width, card_height) // 7)
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
    *,
    dark: bool,
    title_size: int,
    subtitle_size: int,
    max_width: int | None = None,
) -> int:
    theme = _theme(dark)
    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(title_size, bold=True)
    body_font = _load_font(subtitle_size, bold=False)

    wrapped_title = _wrap_text(draw, title, title_font, max_width)
    wrapped_subtitle = _wrap_text(draw, subtitle, body_font, max_width)
    draw.multiline_text(anchor, wrapped_title, fill=theme.text_primary, font=title_font, spacing=6)
    title_box = draw.multiline_textbbox(anchor, wrapped_title, font=title_font, spacing=6)
    subtitle_y = title_box[3] + max(10, subtitle_size // 2)
    draw.multiline_text(
        (anchor[0], subtitle_y),
        wrapped_subtitle,
        fill=theme.text_secondary,
        font=body_font,
        spacing=max(6, subtitle_size // 3),
    )
    subtitle_box = draw.multiline_textbbox(
        (anchor[0], subtitle_y),
        wrapped_subtitle,
        font=body_font,
        spacing=max(6, subtitle_size // 3),
    )
    return subtitle_box[3]


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    max_width: int | None,
) -> str:
    if not text or not max_width or max_width <= 0:
        return text

    wrapped_lines: list[str] = []
    for paragraph in text.splitlines():
        words = paragraph.split()
        if not words:
            wrapped_lines.append("")
            continue

        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                current = candidate
            else:
                wrapped_lines.append(current)
                current = word
        wrapped_lines.append(current)
    return "\n".join(wrapped_lines)


def _draw_pill(
    canvas: Image.Image,
    text: str,
    bounds: Bounds,
    *,
    dark: bool,
    emphasized: bool,
) -> None:
    theme = _theme(dark)
    left, top, right, bottom = bounds
    draw = ImageDraw.Draw(canvas)
    fill = theme.pill_fill if emphasized else theme.card_fill
    stroke = theme.pill_fill if emphasized else theme.card_stroke
    text_color = theme.pill_text if emphasized else theme.text_secondary
    draw.rounded_rectangle(bounds, radius=(bottom - top) // 2, fill=fill, outline=stroke, width=1)
    font = _load_font(18, bold=True)
    text_box = draw.textbbox((0, 0), text, font=font)
    text_x = left + ((right - left) - (text_box[2] - text_box[0])) // 2
    text_y = top + ((bottom - top) - (text_box[3] - text_box[1])) // 2 - 1
    draw.text((text_x, text_y), text, fill=text_color, font=font)


def build_wizard_panel(logo: Image.Image, output: Path, *, dark: bool) -> None:
    size = (404, 772)
    canvas = _build_backdrop(size, dark)
    _rounded_panel(canvas, (24, 26, 380, 744), dark=dark)
    _draw_pill(canvas, "Bao Desktop", (54, 52, 200, 86), dark=dark, emphasized=True)
    _paste_logo_card(canvas, logo, (56, 116, 348, 384), dark=dark)
    _draw_text_block(
        canvas,
        "One calm place\nfor AI work.",
        "Chat, memory, tools, and gateway controls stay aligned from first install.",
        (56, 438),
        dark=dark,
        title_size=40,
        subtitle_size=20,
        max_width=286,
    )
    _draw_pill(canvas, "Desktop chat", (56, 640, 184, 676), dark=dark, emphasized=False)
    _draw_pill(canvas, "Memory", (194, 640, 292, 676), dark=dark, emphasized=False)
    _draw_pill(canvas, "Gateway", (56, 688, 176, 724), dark=dark, emphasized=False)
    canvas.save(output, format="PNG")


def build_wizard_small(logo: Image.Image, output: Path, *, dark: bool) -> None:
    size = (128, 128)
    canvas = _build_backdrop(size, dark)
    _rounded_panel(canvas, (8, 8, 120, 120), dark=dark)
    _paste_logo_card(canvas, logo, (20, 20, 108, 108), dark=dark)
    canvas.save(output, format="PNG")


def build_wizard_back(logo: Image.Image, output: Path, *, dark: bool) -> None:
    size = (1194, 864)
    canvas = _build_backdrop(size, dark)
    _rounded_panel(canvas, (72, 88, 1122, 776), dark=dark)
    _draw_pill(canvas, "Warm setup, fast start", (112, 138, 332, 178), dark=dark, emphasized=True)
    bottom = _draw_text_block(
        canvas,
        "Install Bao once.\nFinish setup in the app.",
        "Keep the installer lightweight. Connect channels and tune your workspace after launch, inside Bao.",
        (112, 214),
        dark=dark,
        title_size=52,
        subtitle_size=22,
        max_width=540,
    )
    _draw_pill(canvas, "Windows setup", (112, bottom + 32, 274, bottom + 68), dark=dark, emphasized=False)
    _draw_pill(canvas, "Local-first config", (286, bottom + 32, 472, bottom + 68), dark=dark, emphasized=False)
    _draw_pill(canvas, "Gateway ready", (112, bottom + 82, 260, bottom + 118), dark=dark, emphasized=False)
    _paste_logo_card(canvas, logo, (774, 164, 1012, 402), dark=dark)
    canvas.save(output, format="PNG")


def build_dmg_background(logo: Image.Image, output: Path, *, dark: bool = False) -> None:
    size = (720, 420)
    theme = _theme(dark)
    canvas = _build_backdrop(size, dark)
    _rounded_panel(canvas, (28, 28, 692, 392), dark=dark)
    _draw_pill(canvas, "Drag to install", (52, 48, 188, 82), dark=dark, emphasized=True)
    _draw_text_block(
        canvas,
        "Move Bao to Applications.",
        "One app. One destination. Open it from Applications when the copy finishes.",
        (52, 102),
        dark=dark,
        title_size=32,
        subtitle_size=18,
        max_width=380,
    )

    app_bounds = (94, 172, 238, 316)
    apps_bounds = (506, 172, 650, 316)
    _paste_logo_card(canvas, logo, app_bounds, dark=dark)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        apps_bounds,
        radius=28,
        fill=theme.card_fill,
        outline=theme.card_stroke,
        width=2,
    )

    folder_tab = (apps_bounds[0] + 18, apps_bounds[1] + 16, apps_bounds[0] + 78, apps_bounds[1] + 44)
    draw.rounded_rectangle(folder_tab, radius=12, fill=theme.pill_fill)
    body_left = apps_bounds[0] + 18
    body_top = apps_bounds[1] + 36
    draw.rounded_rectangle(
        (body_left, body_top, apps_bounds[2] - 18, apps_bounds[3] - 18),
        radius=22,
        fill=(255, 255, 255, 40) if dark else (255, 255, 255, 92),
    )
    label_font = _load_font(18, bold=True)
    label_box = draw.textbbox((0, 0), "Applications", font=label_font)
    label_x = apps_bounds[0] + ((apps_bounds[2] - apps_bounds[0]) - (label_box[2] - label_box[0])) // 2
    label_y = apps_bounds[3] + 12
    draw.text((label_x, label_y), "Applications", fill=theme.text_secondary, font=label_font)

    app_label_box = draw.textbbox((0, 0), "Bao", font=label_font)
    app_label_x = app_bounds[0] + ((app_bounds[2] - app_bounds[0]) - (app_label_box[2] - app_label_box[0])) // 2
    draw.text((app_label_x, app_bounds[3] + 12), "Bao", fill=theme.text_secondary, font=label_font)

    line_y = (app_bounds[1] + app_bounds[3]) // 2
    line_start = app_bounds[2] + 22
    line_end = apps_bounds[0] - 30
    draw.line((line_start, line_y, line_end, line_y), fill=theme.arrow_glow, width=18)
    draw.line((line_start, line_y, line_end, line_y), fill=theme.arrow_line, width=4)
    arrow_points = [
        (line_end - 18, line_y - 16),
        (line_end + 2, line_y),
        (line_end - 18, line_y + 16),
    ]
    draw.line((arrow_points[0], arrow_points[1]), fill=theme.arrow_line, width=4)
    draw.line((arrow_points[1], arrow_points[2]), fill=theme.arrow_line, width=4)

    canvas.save(output, format="PNG")


def _build_all_assets(logo: Image.Image, output_dir: Path, dmg_background: Path) -> list[Path]:
    generated_paths = [
        output_dir / "wizard-image-light.png",
        output_dir / "wizard-image-dark.png",
        output_dir / "wizard-small-light.png",
        output_dir / "wizard-small-dark.png",
        output_dir / "wizard-back-light.png",
        output_dir / "wizard-back-dark.png",
        dmg_background,
    ]
    build_wizard_panel(logo, generated_paths[0], dark=False)
    build_wizard_panel(logo, generated_paths[1], dark=True)
    build_wizard_small(logo, generated_paths[2], dark=False)
    build_wizard_small(logo, generated_paths[3], dark=True)
    build_wizard_back(logo, generated_paths[4], dark=False)
    build_wizard_back(logo, generated_paths[5], dark=True)
    build_dmg_background(logo, generated_paths[6], dark=False)
    return generated_paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate unified Windows installer and macOS DMG brand assets"
    )
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
    _ = parser.add_argument(
        "--dmg-background",
        default="app/resources/dmg-background.png",
        help="Output path for the macOS DMG background image",
    )
    args = parser.parse_args()

    source = Path(cast(str, args.source)).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source logo not found: {source}")

    output_dir = Path(cast(str, args.output_dir)).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    dmg_background = Path(cast(str, args.dmg_background)).expanduser().resolve()
    dmg_background.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as raw_logo:
        logo = raw_logo.convert("RGBA")

    generated_paths = _build_all_assets(logo, output_dir, dmg_background)
    print(f"Generated brand assets in {output_dir} and {dmg_background.parent}")
    for path in generated_paths:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
