#!/usr/bin/env python3
"""Rebuild measurements/frames_index.json by scanning the screenshots dir.

Used when a capture run died before the harness wrote the index, or to
refresh the index mid-run. Filename shape: <stepIndex>_<shot>__<angle>__t<n>.png
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHOTS_DIR = os.path.join(ROOT, "data", "uitest-report", "screenshots",
                         "vfxlab.3_capture")
OUT = os.path.join(ROOT, "data", "capture", "measurements",
                   "frames_index.json")

RX = re.compile(r"^\d+_(.+)__(.+)__t(\d+)\.png$")


def main() -> int:
    idx: dict[str, str] = {}
    for name in sorted(os.listdir(SHOTS_DIR)):
        m = RX.match(name)
        if not m:
            continue
        label = name[name.index("_") + 1:-4]
        idx[label] = os.path.join(SHOTS_DIR, name)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(idx, open(OUT, "w"), indent=1)
    shots = {k.split("__")[0] for k in idx}
    print(f"{len(idx)} frames / {len(shots)} shots -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
