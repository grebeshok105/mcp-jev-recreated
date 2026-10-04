"""Measured layer: fold capture_results.json into passport `measured`.

Each capture shot maps to one catalog resource. Per-angle stats are kept
verbatim; the passport gets an aggregated summary (max spawned, peak alive,
ticks to first visibility, world-space bounds, covered angles/ticks, frame
paths). Missing shots simply contribute nothing — `unknown` stays absent.
"""
from __future__ import annotations

import json
import os
from typing import Any

# shot key in capture_results -> catalog passport id (None = same id)
SHOT_TO_RESOURCE: dict[str, str] = {
    "levelevent_2001": "minecraft:world_event/PARTICLES_DESTROY_BLOCK",
    # quasar emitter passports use the emitter asset id already
}


def shot_resource_id(shot_key: str) -> str:
    if shot_key in SHOT_TO_RESOURCE:
        return SHOT_TO_RESOURCE[shot_key]
    if ":" not in shot_key and "_" in shot_key:
        return shot_key.replace("_", ":", 1)
    return shot_key


def summarize_angles(angles: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"angles": {}}
    spawned_max = peak = 0
    first_visible = None
    bounds_min = bounds_max = None
    frames = []
    for angle, a in angles.items():
        s = int(a.get("spawned", 0))
        pa = int(a.get("peak_alive", 0))
        spawned_max = max(spawned_max, s)
        peak = max(peak, pa)
        fv = a.get("first_visible_tick")
        if fv is not None and str(fv) != "":
            fv_i = int(fv)
            first_visible = fv_i if first_visible is None else min(first_visible, fv_i)
        try:
            mn = [float(x) for x in str(a["bounds_min"]).split(",")]
            mx = [float(x) for x in str(a["bounds_max"]).split(",")]
            bounds_min = mn if bounds_min is None else [min(*p) for p in zip(bounds_min, mn)]
            bounds_max = mx if bounds_max is None else [max(*p) for p in zip(bounds_max, mx)]
        except (KeyError, ValueError):
            pass
        frames.extend(a.get("frames", []))
        out["angles"][angle] = {
            "spawned": s, "peak_alive": pa,
            "alive_at_end": int(a.get("alive_at_end", 0)),
            "frames": [os.path.basename(f) for f in a.get("frames", [])],
            "diagnostics": a.get("diagnostics", []),
        }
    if spawned_max:
        out["spawned_max"] = spawned_max
    if peak:
        out["peak_alive"] = peak
    if first_visible is not None:
        out["first_visible_tick"] = first_visible
    if bounds_min and bounds_max:
        out["bounds_min"] = bounds_min
        out["bounds_max"] = bounds_max
        out["extent_blocks"] = [round(b - a, 3) for a, b in zip(bounds_min, bounds_max)]
    out["angles_covered"] = sorted(angles.keys())
    out["frames_captured"] = len(frames)
    return out


def apply_measured(catalog, capture_results_path: str) -> list[str]:
    """Merge capture results into catalog passports. Returns diagnostics."""
    diags: list[str] = []
    if not os.path.isfile(capture_results_path):
        return [f"measured: artifact missing {capture_results_path}"]
    results = json.load(open(capture_results_path))
    for shot_key, shot in results.items():
        rid = shot_resource_id(shot_key)
        if catalog.get(rid) is None:
            diags.append(f"measured: shot {shot_key} -> {rid} has no passport")
            continue
        m = summarize_angles(shot.get("angles", {}))
        m["capture_kind"] = shot.get("kind")
        from ..catalog.builder import CatalogBuilder
        CatalogBuilder.merge_measured(catalog, rid, m)
    return diags
