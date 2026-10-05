#!/usr/bin/env python3
"""Generate data/capture/capture_plan.json for all spawnable answerable
resources in data/catalog.json.

Kinds covered: particle, parameterized_particle, world_event(has_visual),
fx, quasar_emitter. `composite` resources are Codex vfx parameter bundles
(tuning JSON consumed by ability code, no standalone spawn path) — they are
emitted to the exceptions list instead of the plan.

The resource->shot mapping and spawn-option tuning tables live in
jevlab.scene.spawn_specs so the scene playback lane spawns a resource
exactly the way the catalog capture did.

Usage: python tools/gen_capture_plan.py [--out data/capture/capture_plan.json]
Prints a summary plus the exception list on stdout.
"""
from __future__ import annotations

import argparse
import json
import os

from jevlab.scene.spawn_specs import ANSWERABLE, shot_spec_for

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CATALOG = os.path.join(ROOT, "data", "catalog.json")
LEVEL_EVENTS = os.path.join(ROOT, "data", "capture", "dump", "level_events.json")
DEFAULT_OUT = os.path.join(ROOT, "data", "capture", "capture_plan.json")

COMPOSITE_REASON = ("Codex vfx parameter bundle (tuning JSON consumed by "
                    "ability code; no standalone emitter/asset to spawn - "
                    "verified: file contains only scalar tuning fields)")


def build_shots() -> tuple[list[dict], list[dict], dict]:
    catalog = json.load(open(CATALOG))
    events = {e["name"]: int(e["id"])
              for e in json.load(open(LEVEL_EVENTS))["events"]}
    shots: list[dict] = []
    exceptions: list[dict] = []
    counts: dict[str, int] = {}
    for r in catalog["resources"]:
        if not r.get("ready_to_use") or r["kind"] not in ANSWERABLE:
            continue
        if r["kind"] == "world_event" and not r["factual"].get("has_visual"):
            continue
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
        shot, reason = shot_spec_for(r, events)
        if shot is None:
            exceptions.append({
                "id": r["id"], "kind": r["kind"],
                "reason": COMPOSITE_REASON if r["kind"] == "composite" else reason,
            })
            continue
        shots.append(shot)
    return shots, exceptions, counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--kinds", default=None,
                    help="comma-separated shot kinds to include")
    args = ap.parse_args()
    shots, exceptions, counts = build_shots()
    if args.kinds:
        keep = set(args.kinds.split(","))
        shots = [s for s in shots if s["kind"] in keep]
    plan = {
        "version": 1,
        "scene": {"pos": [8.5, 2, 8.5], "time": 6000, "weather": "clear"},
        "defaults": {"frames": [3, 8, 20], "max_ticks": 30,
                     "angles": ["front", "threequarter", "top"]},
        "shots": shots,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(plan, fh, indent=1)
    print(f"wrote {len(shots)} shots -> {args.out}")
    print("answerable by kind:", counts)
    print(f"exceptions: {len(exceptions)}")
    for e in exceptions:
        print("  -", e["id"], "|", e["reason"])


if __name__ == "__main__":
    main()
