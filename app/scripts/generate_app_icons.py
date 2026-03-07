from __future__ import annotations

import argparse
import importlib
import shutil
import subprocess
import tempfile
from pathlib import Path


def _build_rounded_base(source: Path, size: int = 1024):
    image_mod = importlib.import_module("PIL.Image")
    image_chops_mod = importlib.import_module("PIL.ImageChops")
    image_draw_mod = importlib.import_module("PIL.ImageDraw")
    image_filter_mod = importlib.import_module("PIL.ImageFilter")

    img = image_mod.open(source).convert("RGBA")
    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    square = img.crop((left, top, left + side, top + side))

    canvas = image_mod.new("RGBA", (size, size), (0, 0, 0, 0))
    inner = int(size * 0.88)
    radius = int(inner * 0.24)

    artwork = square.resize((inner, inner), image_mod.Resampling.LANCZOS)
    mask = image_mod.new("L", (inner, inner), 0)
    draw = image_draw_mod.Draw(mask)
    draw.rounded_rectangle((0, 0, inner - 1, inner - 1), radius=radius, fill=255)

    # Soft drop shadow for depth.
    shadow = image_mod.new("RGBA", (inner, inner), (0, 0, 0, 0))
    shadow_alpha = image_mod.new("L", (inner, inner), 0)
    image_draw_mod.Draw(shadow_alpha).rounded_rectangle(
        (0, 0, inner - 1, inner - 1), radius=radius, fill=170
    )
    shadow_alpha = shadow_alpha.filter(image_filter_mod.GaussianBlur(max(2, size // 120)))
    shadow.putalpha(shadow_alpha)

    layer = image_mod.new("RGBA", (inner, inner), (0, 0, 0, 0))
    layer.paste(artwork, (0, 0), mask)

    # Top gloss highlight.
    highlight_alpha = image_mod.new("L", (inner, inner), 0)
    hdraw = image_draw_mod.Draw(highlight_alpha)
    top_stop = int(inner * 0.62)
    for y in range(top_stop):
        t = y / max(1, top_stop - 1)
        alpha = int((1.0 - t) ** 1.6 * 105)
        hdraw.line((0, y, inner, y), fill=alpha)
    highlight_alpha = image_chops_mod.multiply(highlight_alpha, mask)
    highlight = image_mod.new("RGBA", (inner, inner), (255, 255, 255, 0))
    highlight.putalpha(highlight_alpha)

    # Bottom tonal shade.
    shade_alpha = image_mod.new("L", (inner, inner), 0)
    sdraw = image_draw_mod.Draw(shade_alpha)
    start = int(inner * 0.58)
    for y in range(start, inner):
        t = (y - start) / max(1, inner - start - 1)
        alpha = int((t**1.2) * 38)
        sdraw.line((0, y, inner, y), fill=alpha)
    shade_alpha = image_chops_mod.multiply(shade_alpha, mask)
    shade = image_mod.new("RGBA", (inner, inner), (0, 0, 0, 0))
    shade.putalpha(shade_alpha)

    # Subtle glossy stroke.
    stroke = image_mod.new("RGBA", (inner, inner), (0, 0, 0, 0))
    stroke_draw = image_draw_mod.Draw(stroke)
    stroke_w = max(2, size // 256)
    stroke_draw.rounded_rectangle(
        (stroke_w // 2, stroke_w // 2, inner - 1 - stroke_w // 2, inner - 1 - stroke_w // 2),
        radius=max(1, radius - stroke_w // 2),
        outline=(255, 255, 255, 88),
        width=stroke_w,
    )

    offset = (size - inner) // 2
    canvas.alpha_composite(shadow, (offset, offset + max(1, size // 72)))
    canvas.alpha_composite(layer, (offset, offset))
    canvas.alpha_composite(highlight, (offset, offset))
    canvas.alpha_composite(shade, (offset, offset))
    canvas.alpha_composite(stroke, (offset, offset))
    return canvas


def _save_ico(base, output: Path) -> None:
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    output.parent.mkdir(parents=True, exist_ok=True)
    base.save(output, format="ICO", sizes=sizes)


def _save_icns(base, output: Path) -> None:
    image_mod = importlib.import_module("PIL.Image")
    iconutil = shutil.which("iconutil")
    if not iconutil:
        raise RuntimeError("iconutil not found; generate .icns on macOS only")

    with tempfile.TemporaryDirectory(prefix="Bao-iconset-") as tmp:
        iconset = Path(tmp) / "logo.iconset"
        iconset.mkdir(parents=True, exist_ok=True)

        sizes = [
            (16, "icon_16x16.png"),
            (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"),
            (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"),
            (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"),
            (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"),
            (1024, "icon_512x512@2x.png"),
        ]
        for px, name in sizes:
            base.resize((px, px), image_mod.Resampling.LANCZOS).save(iconset / name, format="PNG")

        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [iconutil, "-c", "icns", str(iconset), "-o", str(output)],
            check=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate rounded macOS/Windows desktop icons from a JPG logo"
    )
    parser.add_argument(
        "--source", default="assets/logo.jpg", help="Source image path (default: assets/logo.jpg)"
    )
    parser.add_argument("--ico", default="app/resources/logo.ico", help="Output .ico path")
    parser.add_argument("--icns", default="assets/logo.icns", help="Output .icns path")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source logo not found: {source}")

    base = _build_rounded_base(source)
    _save_ico(base, Path(args.ico).expanduser().resolve())
    _save_icns(base, Path(args.icns).expanduser().resolve())
    print("Generated rounded icons:")
    print(f"- {Path(args.ico).expanduser().resolve()}")
    print(f"- {Path(args.icns).expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
