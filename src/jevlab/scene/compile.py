"""Compile a validated scene spec into the probe playback plan
(`scene_plan.json`) that the Java SceneRun scenario executes.

Shot specs come from the same resource->shot mapping the catalog capture
planner uses (jevlab.scene.spawn_specs.shot_spec_for), so a scene step
spawns the resource exactly the way the measured/visual capture did — user
options merge over the tuned defaults.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .spawn_specs import shot_spec_for
from .spec import SceneValidation, validate_scene


def load_level_events(path: str) -> dict[str, int]:
    data = json.load(open(path))
    return {e["name"]: int(e["id"]) for e in data["events"]}


def compile_scene(spec: dict, catalog_index: dict[str, dict],
                  events: dict[str, int]) -> tuple[dict | None, SceneValidation]:
    """Validate + compile. Returns (plan, validation).

    plan is the probe scene_plan.json document; None when validation failed.
    """
    v = validate_scene(spec, catalog_index)
    if not v.ok:
        return None, v
    n = v.normalized
    steps: list[dict[str, Any]] = []
    for s in n["steps"]:
        res = catalog_index[s["id"]]
        shot, reason = shot_spec_for(res, events)
        if shot is None:
            # validate_scene already rejects non-spawnable kinds; this is a
            # belt-and-braces guard for mapping drift.
            v.errors.append(f"'{s['id']}': {reason}")
            return None, v
        merged_opts = dict(shot.get("options") or {})
        merged_opts.update(s.get("options") or {})
        out_shot = dict(shot)
        out_shot["options"] = merged_opts
        if s["id"] != shot["id"]:
            # level_event shots carry a synthetic id; keep the resource id so
            # results index by what the caller asked for.
            out_shot["resource_id"] = s["id"]
        if s["stop_after"]:
            out_shot["stop_after"] = True
        steps.append({"at_tick": s["at_tick"], "pos": s["pos"],
                      "shot": out_shot})
    plan = {
        "version": 1,
        "name": n["name"],
        "scene": n["scene"],
        "camera": n["camera"],
        "frames": n["frames"],
        "duration": n["duration"],
        "steps": steps,
    }
    return plan, v


def write_plan(plan: dict, path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(plan, fh, indent=1)
    return path
