#!/usr/bin/env python3
"""Partition capture_plan shots into round-robin batches for sub-agent
visual passes, so each batch mixes kinds (particles, world events, quasar).

Usage: python tools/build_batches.py --batches 10 [--out data/capture/batches.json]
Writes {"batches": [[shot_key, ...], ...]}
"""
from __future__ import annotations

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLAN = os.path.join(ROOT, "data", "capture", "capture_plan.json")


def sanitize(sid: str) -> str:
    return sid.replace(":", "_").replace("/", "_")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=int, default=10)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "capture",
                                                "batches.json"))
    args = ap.parse_args()
    plan = json.load(open(PLAN))
    keys = [sanitize(s["id"]) for s in plan["shots"]]
    seen = set()
    uniq = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    batches = [[] for _ in range(args.batches)]
    for i, k in enumerate(uniq):
        batches[i % args.batches].append(k)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"batches": batches}, open(args.out, "w"), indent=1)
    for i, b in enumerate(batches):
        print(f"batch {i}: {len(b)} shots  first={b[0]} last={b[-1]}")
    print(f"total {len(uniq)} shots -> {args.out}")


if __name__ == "__main__":
    main()
