#!/usr/bin/env python3
"""Build per-shot contact sheets from capture frames_index.json.

Layout: one row per camera angle (front, threequarter, top), one column per
tick. Each cell is a downscaled frame with a small label bar `<angle> t<n>`.
Output: data/capture/sheets/<shot>.png

Usage: python tools/make_sheets.py
"""
from __future__ import annotations

import json
import os
import re

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FRAMES_INDEX = os.path.join(ROOT, "data", "capture", "measurements",
                            "frames_index.json")
OUT_DIR = os.path.join(ROOT, "data", "capture", "sheets")

CELL_W, CELL_H = 426, 342
LABEL_H = 14
ANGLE_ORDER = ["front", "threequarter", "top"]


def tick_of(tk: str) -> int:
    m = re.match(r"t(\d+)", tk)
    return int(m.group(1)) if m else 0


def main() -> None:
    idx = json.load(open(FRAMES_INDEX))
    shots: dict[str, dict[str, dict[int, str]]] = {}
    for label, path in idx.items():
        parts = label.split("__")
        if len(parts) != 3 or not os.path.isfile(path):
            continue
        shot, angle, tick = parts
        shots.setdefault(shot, {}).setdefault(angle, {})[tick_of(tick)] = path
    os.makedirs(OUT_DIR, exist_ok=True)
    for shot, angles in sorted(shots.items()):
        ticks = sorted({t for a in angles.values() for t in a})
        rows = [a for a in ANGLE_ORDER if a in angles] + \
               sorted(set(angles) - set(ANGLE_ORDER))
        grid_w = CELL_W * len(ticks)
        grid_h = (CELL_H + LABEL_H) * len(rows)
        grid = Image.new("RGB", (grid_w, grid_h), (24, 24, 24))
        draw = ImageDraw.Draw(grid)
        for r, angle in enumerate(rows):
            for c, tick in enumerate(ticks):
                x, y = c * CELL_W, r * (CELL_H + LABEL_H)
                draw.rectangle([x, y, x + CELL_W, y + LABEL_H], fill=(40, 40, 48))
                draw.text((x + 4, y + 2), f"{angle} t{tick}", fill=(220, 220, 220))
                path = angles[angle].get(tick)
                if not path:
                    draw.text((x + 8, y + LABEL_H + 40), "(no frame)", fill=(120, 120, 120))
                    continue
                with Image.open(path) as im:
                    im.thumbnail((CELL_W, CELL_H), Image.BILINEAR)
                    grid.paste(im, (x, y + LABEL_H))
        grid.save(os.path.join(OUT_DIR, f"{shot}.png"))
    print(f"wrote {len(shots)} sheets -> {OUT_DIR}")


if __name__ == "__main__":
    main()
