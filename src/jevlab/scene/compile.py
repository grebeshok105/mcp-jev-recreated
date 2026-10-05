"""Compile a validated scene spec into the probe playback plan
(`scene_plan.json`) that the Java SceneRun scenario executes.

Shot specs come from the same resource->shot mapping the catalog capture
planner uses (jevlab.scene.spawn_specs.shot_spec_for), so a scene step
spawns the resource exactly the way the measured/visual capture did — user
options merge over the tuned defaults.

v2: repeat/group expansion happens here at compile time — the Java runtime
just fires one spawn per expanded step at its absolute tick.
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


def _repeat_offsets(rep: dict | None, base: int, duration: int) -> list[int]:
    """Tick offsets a repeat produces relative to `base`; [0] when absent.
    Expansion is clipped to [0, duration)."""
    if not rep:
        return [0]
    every = rep["every"]
    out: list[int] = []
    if "count" in rep:
        for k in range(rep["count"]):
            off = k * every
            if base + off < duration:
                out.append(off)
    else:  # until — fires at base, base+every, ... while < until
        k = 0
        while base + k * every < rep["until"]:
            out.append(k * every)
            k += 1
    return out or [0]


def _expand_ticks(step: dict, duration: int) -> list[int]:
    """Absolute ticks this step spawns at: own repeat inside group repeat."""
    base = step["at_tick"]  # already includes the group's tick shift
    own = _repeat_offsets(step.get("repeat"), base, duration)
    grp = step.get("group_repeat")
    if not grp:
        return sorted(set(base + o for o in own))
    out: list[int] = []
    for g_off in _repeat_offsets(grp, base, duration):
        for o in own:
            t = base + g_off + o
            if t < duration:
                out.append(t)
    return sorted(set(out))


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
        for t in _expand_ticks(s, n["duration"]):
            step: dict[str, Any] = {"at_tick": t, "pos": s["pos"],
                                    "shot": out_shot}
            if s["name"]:
                step["name"] = s["name"]
            if s["at"]:
                step["at"] = s["at"]
            if s["to"]:
                step["to"] = s["to"]
            if s["follow"]:
                step["follow"] = s["follow"]
            if s["track"]:
                step["track"] = s["track"]
            steps.append(step)
    plan = {
        "version": 2,
        "name": n["name"],
        "scene": n["scene"],
        "camera": n["camera"],
        "frames": n["frames"],
        "duration": n["duration"],
        "steps": steps,
        "commands": n["commands"],
    }
    return plan, v


def write_plan(plan: dict, path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(plan, fh, indent=1)
    return path
