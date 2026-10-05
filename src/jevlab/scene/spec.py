"""Scene spec validation.

A scene spec is a small JSON document describing one staged playback: a
camera anchor, a timeline of spawn steps (resource id + tick + local offset)
and the frame ticks to screenshot. `validate_scene` checks every step
against the catalog and returns errors (invalid, nothing is compiled) plus
warnings (valid but worth knowing: requires_water, catalog capture missed
the effect, ...).

Normalized form after validation:
    {
      "name": str,
      "scene": {"pos": [x, lift, z], "time": int, "weather": str},
      "camera": {"angles": [str]},
      "frames": [int],          # sorted unique positive ticks
      "duration": int,          # ticks the timeline runs
      "steps": [
        {"at_tick": int, "id": str, "kind": str, "pos": [dx,dy,dz],
         "options": dict, "stop_after": bool}
      ]
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .spawn_specs import PARAM_SPECS

KNOWN_ANGLES = {"front", "back", "side", "side_right", "top",
                "threequarter", "low", "far"}

SPAWNABLE_KINDS = {"particle", "parameterized_particle", "world_event",
                   "fx", "quasar_emitter"}

# passport parameter_schema key -> spawn options key. Everything not listed
# maps to itself.
SCHEMA_TO_OPTION = {
    "block_state": "block",
    "item": "item",
}

OPTION_KEY_BY_SCHEMA = SCHEMA_TO_OPTION


@dataclass
class SceneValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized: dict | None = None


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_param(schema_key: str, pschema: dict, options: dict,
                 step_label: str, errors: list[str]) -> None:
    opt_key = SCHEMA_TO_OPTION.get(schema_key, schema_key)
    spec = pschema.get(schema_key) or {}
    has_default = "default" in spec
    if opt_key not in options:
        if not has_default:
            errors.append(f"{step_label}: missing required parameter "
                          f"'{schema_key}' (option '{opt_key}')")
        return
    v = options[opt_key]
    t = spec.get("type")
    if t == "rgb" and not (isinstance(v, list) and len(v) == 3
                           and all(_is_num(c) for c in v)):
        errors.append(f"{step_label}: '{opt_key}' must be [r,g,b] numbers")
    elif t == "float" and not _is_num(v):
        errors.append(f"{step_label}: '{opt_key}' must be a number")
    elif t == "int" and not isinstance(v, int):
        errors.append(f"{step_label}: '{opt_key}' must be an int")
    elif t == "blockstate" and not isinstance(v, str):
        errors.append(f"{step_label}: '{opt_key}' must be a block id string")
    elif t == "position_source" and not (
            isinstance(v, list) and len(v) == 3 and all(_is_num(c) for c in v)):
        errors.append(f"{step_label}: '{opt_key}' must be [x,y,z] numbers")


def validate_scene(spec: dict, catalog_index: dict[str, dict],
                   *, max_duration: int = 20 * 60 * 5) -> SceneValidation:
    """Validate a scene spec against the catalog.

    `catalog_index` maps resource id -> catalog passport dict.
    Returns SceneValidation; `normalized` is set iff ok.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(spec, dict):
        return SceneValidation(ok=False, errors=["scene spec must be an object"])

    name = spec.get("name") or "scene"
    scene_in = spec.get("scene") or {}
    pos = scene_in.get("pos", [8.5, 2.0, 8.5])
    if not (isinstance(pos, list) and 1 <= len(pos) <= 3
            and all(_is_num(c) for c in pos)):
        errors.append("scene.pos must be [x, lift, z] numbers")
        pos = [8.5, 2.0, 8.5]
    while len(pos) < 3:
        pos.append(2.0 if len(pos) == 1 else 8.5)
    scene = {
        "pos": pos,
        "time": int(scene_in.get("time", 6000)),
        "weather": str(scene_in.get("weather", "clear")),
    }

    cam_in = spec.get("camera") or {}
    angles = cam_in.get("angles") or spec.get("angles") or ["front"]
    if not isinstance(angles, list) or not angles:
        errors.append("camera.angles must be a non-empty list")
        angles = []
    else:
        for a in angles:
            if a not in KNOWN_ANGLES:
                errors.append(f"unknown camera angle '{a}' "
                              f"(known: {sorted(KNOWN_ANGLES)})")

    duration = spec.get("duration", 60)
    if not isinstance(duration, int) or duration <= 0 or duration > max_duration:
        errors.append(f"duration must be an int in 1..{max_duration}")
        duration = 60

    frames = spec.get("frames") or [3, 8, 20]
    if not isinstance(frames, list) or not all(
            isinstance(f, int) and f > 0 for f in frames):
        errors.append("frames must be a list of positive ints")
        frames = []
    else:
        frames = sorted(set(f for f in frames if f <= duration))
        if not frames:
            warnings.append("no frame ticks within duration — nothing will "
                            "be screenshotted")

    steps_in = spec.get("steps")
    if not isinstance(steps_in, list) or not steps_in:
        errors.append("steps must be a non-empty list")
        steps_in = []

    steps: list[dict] = []
    for i, s in enumerate(steps_in):
        label = f"steps[{i}]"
        if not isinstance(s, dict):
            errors.append(f"{label}: must be an object")
            continue
        rid = s.get("id")
        tick = s.get("tick", s.get("at_tick", 0))
        if not isinstance(tick, int) or tick < 0 or tick >= duration:
            errors.append(f"{label}: tick must be an int in 0..{duration - 1}")
            continue
        if not isinstance(rid, str):
            errors.append(f"{label}: 'id' must be a resource id string")
            continue
        res = catalog_index.get(rid)
        if res is None:
            errors.append(f"{label}: unknown resource '{rid}'")
            continue
        kind = res.get("kind")
        if not res.get("ready_to_use"):
            errors.append(f"{label}: '{rid}' is not ready_to_use")
            continue
        if kind not in SPAWNABLE_KINDS:
            reason = ("composite tuning bundles have no standalone spawn path"
                      if kind == "composite" else
                      f"kind '{kind}' is not spawnable in the scene lane")
            errors.append(f"{label}: '{rid}' — {reason}")
            continue
        if kind == "world_event" and not res.get("factual", {}).get("has_visual"):
            errors.append(f"{label}: world_event '{rid}' has no visual output")
            continue

        lpos = s.get("pos", [0.0, 0.0, 0.0])
        if not (isinstance(lpos, list) and len(lpos) == 3
                and all(_is_num(c) for c in lpos)):
            errors.append(f"{label}: pos must be [dx,dy,dz] numbers")
            continue

        options = s.get("options") or {}
        if not isinstance(options, dict):
            errors.append(f"{label}: options must be an object")
            continue

        pschema = res.get("parameter_schema") or {}
        # check params against what the spawner will actually receive:
        # tuned defaults for the id + user overrides
        effective = dict(PARAM_SPECS.get(rid, {}))
        effective.update(options)
        for sk in pschema:
            _check_param(sk, pschema, effective, f"{label} '{rid}'", errors)

        vs = res.get("visual_status")
        vsr = res.get("visual_status_reason")
        if vs == "environment_mismatch":
            warnings.append(f"{label}: '{rid}' {vs}:{vsr} — the dry air scene "
                            f"will most likely show nothing")
        elif vs == "capture_failed":
            warnings.append(f"{label}: '{rid}' {vs}:{vsr} — catalog capture "
                            f"placed it offscreen; check the framing")

        steps.append({
            "at_tick": tick,
            "id": rid,
            "kind": kind,
            "pos": [float(c) for c in lpos],
            "options": options,
            "stop_after": bool(s.get("stop_after", True)),
        })

    steps.sort(key=lambda x: x["at_tick"])
    if errors:
        return SceneValidation(ok=False, errors=errors, warnings=warnings)
    return SceneValidation(
        ok=True, errors=[], warnings=warnings,
        normalized={
            "name": name,
            "scene": scene,
            "camera": {"angles": angles},
            "frames": frames,
            "duration": duration,
            "steps": steps,
        })
