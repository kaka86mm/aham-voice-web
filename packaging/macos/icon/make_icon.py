#!/usr/bin/env python3
"""Generate the AhamVoice macOS app icon (AhamVoice.icns) + a 1024 PNG preview.

Pure Pillow + numpy (no SVG renderer needed). Design: an Aham steel-blue
rounded-square (squircle-ish) with a centered white voice/waveform mark.

Run with the project venv:
    "<venv-python>" packaging/macos/icon/make_icon.py
Produces, next to this file:
    AhamVoice.icns   — bundled by build_app.sh (CFBundleIconFile)
    AhamVoice-1024.png — preview / source raster
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
S = 1024

# ---- Aham steel-blue vertical gradient background ----
TOP = np.array([74, 123, 184], dtype=float)   # #4A7BB8
BOT = np.array([23, 53, 86], dtype=float)      # #173556
ys = np.linspace(0.0, 1.0, S)[:, None]          # (S,1)
col = TOP[None, :] * (1 - ys) + BOT[None, :] * ys  # (S,3)
bg = np.repeat(col[:, None, :], S, axis=1).astype(np.uint8)  # (S,S,3)
bg_img = Image.fromarray(bg, "RGB").convert("RGBA")

# ---- squircle mask (rounded rect with generous radius + small margin) ----
MARGIN = 100
RADIUS = 205
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle(
    [MARGIN, MARGIN, S - MARGIN, S - MARGIN], radius=RADIUS, fill=255
)

icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
icon.paste(bg_img, (0, 0), mask)

# subtle top sheen, clipped to the squircle
sheen = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(sheen).rounded_rectangle(
    [MARGIN, MARGIN, S - MARGIN, int(MARGIN + (S - 2 * MARGIN) * 0.46)],
    radius=RADIUS, fill=(255, 255, 255, 30),
)
sheen.putalpha(ImageChops.multiply(sheen.getchannel("A"), mask))
icon = Image.alpha_composite(icon, sheen)

# ---- centered white voice/waveform: 5 rounded bars ----
BARS = [0.36, 0.66, 1.0, 0.66, 0.36]
W = 84          # bar width
GAP = 52        # gap between bars
MAXH = 470      # tallest bar height
n = len(BARS)
total = n * W + (n - 1) * GAP
x0 = (S - total) // 2
cy = S // 2

def draw_bars(layer: Image.Image, fill) -> None:
    d = ImageDraw.Draw(layer)
    for i, f in enumerate(BARS):
        h = MAXH * f
        x = x0 + i * (W + GAP)
        d.rounded_rectangle([x, cy - h / 2, x + W, cy + h / 2], radius=W / 2, fill=fill)

# soft drop shadow for depth (stays well inside the squircle, no edge bleed)
shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
draw_bars(shadow, (8, 22, 40, 150))
shadow = shadow.filter(ImageFilter.GaussianBlur(16))
shadow = ImageChops.offset(shadow, 0, 12)
icon = Image.alpha_composite(icon, shadow)

bars_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
draw_bars(bars_layer, (255, 255, 255, 255))
icon = Image.alpha_composite(icon, bars_layer)

# ---- write preview + iconset + icns ----
png_path = HERE / "AhamVoice-1024.png"
icon.save(png_path)
print(f"wrote {png_path}")

iconset = Path("/tmp/AhamVoice.iconset")
if iconset.exists():
    import shutil
    shutil.rmtree(iconset)
iconset.mkdir(parents=True)
for s in (16, 32, 128, 256, 512):
    icon.resize((s, s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}.png")
    icon.resize((s * 2, s * 2), Image.LANCZOS).save(iconset / f"icon_{s}x{s}@2x.png")

icns_path = HERE / "AhamVoice.icns"
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns_path)], check=True)
print(f"wrote {icns_path}")
