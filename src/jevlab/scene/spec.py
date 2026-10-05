"""Scene spec v2 — validation.

A scene spec stages catalog resources on a tick timeline inside the probe
world. Grammar v2 adds entity/camera anchors, look-based directions, follow,
keyframe tracks, repeat expansion, step groups and `ref:` cross-step wiring.
One spec drives both preview and real gameplay playback — the probe
(`vfxlab.4_scene`) is the only runtime; validation errors/warnings state
exactly what the runtime will do (no editor-only interpretations).

User-facing step shape (steps[] and groups[].steps[]):
    {
      "name": "mouth_ring",               # optional; required to be ref'd
      "tick": 2,                          # first spawn tick (relative inside groups)
      "id": "minecraft:sonic_boom",
      "anchor": "player.head",            # scene | player[.feet|.chest|.head|.look]
                                          #   | camera | ref:<step name>
      "offset": [0, 0, 0.25],             # local frame of resolved direction
      "direction": "player.look",         # world | player.look | [yaw,pitch]
                                          #   | {"face": <anchor expr>}
      "distance": 8,                      # extra blocks along the direction
      "pos": [0, 0, 0],                   # extra offset in the anchor frame
      "follow": "player",                 # re-resolve anchor every tick
                                          #   (persistent kinds only)
      "track": {"pos": [[t,x,y,z], ...],  # keyframes, lerp'd
                "rotation": [[t,yaw,pitch], ...],   # fx only
                "scale": [[t,s], ...]},             # fx only
      "to": <anchor expr>,                # direction faces this point
      "repeat": {"every": T, "count": N}  # | {"every": T, "until": M},
      "stop_after": true,
      "options": {"destination": "ref:zap", ...}   # ref:<name> -> its pos
    }

Groups: {"tick": T, "repeat": {...}, "steps": [...]} — member ticks are
relative to the group's tick; repeat re-fires the whole group.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from .spawn_specs import PARAM_SPECS

KNOWN_ANGLES = {"front", "back", "side", "side_right", "top",
                "threequarter", "low", "far"}

SPAWNABLE_KINDS = {"particle", "parameterized_particle", "world_event",
                   "fx", "quasar_emitter"}

#: kinds whose spawned object stays steerable after spawn
PERSISTENT_KINDS = {"fx", "quasar_emitter"}

ANCHOR_BASES = {"scene", "player", "player.feet", "player.chest",
                "player.head", "player.look", "camera"}

FOLLOW_TARGETS = {"player"}

# passport parameter_schema key -> spawn options key (rest map to themselves)
SCHEMA_TO_OPTION = {
    "block_state": "block",
    "item": "item",
}


@dataclass
class SceneValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized: dict | None = None


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) \
        and math.isfinite(v)


def _vec3(v: Any) -> bool:
    return isinstance(v, list) and len(v) == 3 and all(_is_num(c) for c in v)


def _validate_anchor_expr(expr: Any, label: str, field_name: str,
                          errors: list[str], depth: int = 0) -> dict | None:
    """Normalize an anchor expression to the object form
    {anchor, offset?, direction?, distance?}. Returns the normalized dict or
    None (errors recorded)."""
    if depth > 4:
        errors.append(f"{label}: {field_name} — anchor expr too deeply nested")
        return None
    if isinstance(expr, str):
        expr = {"anchor": expr}
    if not isinstance(expr, dict):
        errors.append(f"{label}: {field_name} must be an anchor string or object")
        return None
    anchor = expr.get("anchor", "scene")
    if not isinstance(anchor, str):
        errors.append(f"{label}: {field_name}.anchor must be a string")
        return None
    if anchor not in ANCHOR_BASES and not anchor.startswith("ref:"):
        errors.append(
            f"{label}: {field_name}.anchor '{anchor}' unknown "
            f"(known: {sorted(ANCHOR_BASES)}, or ref:<step name>)")
    for k in expr:
        if k not in ("anchor", "offset", "direction", "distance"):
            errors.append(f"{label}: {field_name}.{k} unknown "
                          f"(anchor, offset, direction, distance)")
    out = {"anchor": anchor}
    off = expr.get("offset")
    if off is not None:
        if not _vec3(off):
            errors.append(f"{label}: {field_name}.offset must be [x,y,z]")
        else:
            out["offset"] = [float(c) for c in off]
    dist = expr.get("distance")
    if dist is not None:
        if not _is_num(dist):
            errors.append(f"{label}: {field_name}.distance must be a number")
        else:
            out["distance"] = float(dist)
    d = expr.get("direction")
    if d is not None:
        nd = _validate_direction(d, label, field_name, errors, depth)
        if nd is not None:
            out["direction"] = nd
    if "distance" in out and "direction" not in out and anchor.startswith(
            ("player", "camera")):
        # the overwhelmingly-intended meaning of {"anchor":"player.look",
        # "distance":8} is "8 blocks along the look" — make it explicit
        out["direction"] = "player.look"
    return out


def _validate_direction(d: Any, label: str, field_name: str,
                        errors: list[str], depth: int) -> Any:
    if isinstance(d, str):
        if d in ("world", "player.look"):
            return d
        errors.append(f"{label}: {field_name}.direction '{d}' unknown "
                      f"(world | player.look | [yaw,pitch] | {{face: ...}})")
        return None
    if isinstance(d, list):
        if len(d) == 2 and all(_is_num(c) for c in d):
            return [float(d[0]), float(d[1])]
        errors.append(f"{label}: {field_name}.direction must be [yaw,pitch]")
        return None
    if isinstance(d, dict) and "face" in d:
        inner = _validate_anchor_expr(d["face"], label,
                                      field_name + ".direction.face",
                                      errors, depth + 1)
        return {"face": inner} if inner is not None else None
    errors.append(f"{label}: {field_name}.direction unsupported form")
    return None


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
    if isinstance(v, str) and v.startswith("ref:"):
        if t is not None and t != "position_source":
            errors.append(f"{step_label}: ref: substitution produces a "
                          f"world position — '{opt_key}' expects {t}")
        return  # ref targets are resolved at runtime
    if t == "rgb" and not _vec3(v):
        errors.append(f"{step_label}: '{opt_key}' must be [r,g,b] numbers")
    elif t == "float" and not _is_num(v):
        errors.append(f"{step_label}: '{opt_key}' must be a number")
    elif t == "int" and not _is_int(v):
        errors.append(f"{step_label}: '{opt_key}' must be an int")
    elif t == "blockstate" and not isinstance(v, str):
        errors.append(f"{step_label}: '{opt_key}' must be a block id string")
    elif t == "position_source" and not _vec3(v):
        errors.append(f"{step_label}: '{opt_key}' must be [x,y,z] numbers")


def _validate_track(track: Any, label: str, kind: str,
                    errors: list[str], warnings: list[str]) -> dict | None:
    if track is None:
        return None
    if not isinstance(track, dict):
        errors.append(f"{label}: track must be an object")
        return None
    for k in track:
        if k not in ("pos", "rotation", "scale"):
            warnings.append(f"{label}: track.{k} unknown — dropped "
                            f"(known keys: pos, rotation, scale)")
    out: dict[str, list] = {}
    for key, arity in (("pos", 3), ("rotation", 2), ("scale", 1)):
        if key not in track:
            continue
        rows = track[key]
        if not isinstance(rows, list) or not rows:
            errors.append(f"{label}: track.{key} must be a non-empty list of "
                          f"[tick, value...] rows")
            continue
        bad = [r for r in rows
               if not (isinstance(r, list) and len(r) == arity + 1
                       and _is_int(r[0]) and r[0] >= 0
                       and all(_is_num(c) for c in r[1:]))]
        if bad:
            errors.append(f"{label}: track.{key} rows must be "
                          f"[tick:int, {arity} numbers]")
            continue
        out[key] = [[r[0]] + [float(c) for c in r[1:]] for r in rows]
    if kind not in PERSISTENT_KINDS and out:
        warnings.append(f"{label}: '{kind}' is instantaneous — track has "
                        f"nothing to steer and will be ignored at runtime")
    # channels that exist per kind: fx gets pos/rotation/scale, quasar pos
    if kind == "quasar_emitter":
        allowed = {"pos"}
    elif kind in PERSISTENT_KINDS:
        allowed = {"pos", "rotation", "scale"}
    else:
        allowed = set()
    for k in out:
        if k not in allowed:
            errors.append(f"{label}: track.{k} has no channel on "
                          f"{kind}")
    return out or None


def _validate_repeat(rep: Any, label: str, duration: int,
                     errors: list[str], warnings: list[str] | None = None,
                     base_tick: int = 0) -> dict | None:
    if rep is None:
        return None
    if not isinstance(rep, dict):
        errors.append(f"{label}: repeat must be an object")
        return None
    every = rep.get("every")
    count = rep.get("count")
    until = rep.get("until")
    if not _is_int(every) or every <= 0:
        errors.append(f"{label}: repeat.every must be an int > 0")
        return None
    if (count is None) == (until is None):
        errors.append(f"{label}: repeat needs exactly one of count/until")
        return None
    if count is not None:
        if not _is_int(count) or count < 1:
            errors.append(f"{label}: repeat.count must be an int >= 1")
            return None
        return {"every": every, "count": count}
    if not _is_int(until) or until <= 0 or until > duration:
        errors.append(f"{label}: repeat.until must be an int in 1..{duration}")
        return None
    if until <= base_tick:
        warnings.append(f"{label}: repeat.until {until} <= step tick "
                        f"{base_tick} — no repeat window, fires once")
    return {"every": every, "until": until}


def _expr_refs(expr: dict | None, found: list[str]) -> None:
    """Walk an anchor expr AND its nested face chains for ref: names."""
    if not expr:
        return
    a = expr.get("anchor", "")
    if a.startswith("ref:"):
        found.append(a[4:])
    d = expr.get("direction")
    if isinstance(d, dict) and isinstance(d.get("face"), dict):
        _expr_refs(d["face"], found)


def _stop_after(s: dict, label: str, warnings: list[str]) -> bool:
    v = s.get("stop_after", True)
    if not isinstance(v, bool):
        warnings.append(f"{label}: stop_after must be a boolean "
                        f"(got {v!r} — treated as true)")
        return True
    return v


def _ref_names(options: dict, anchor: dict | None, to: dict | None,
               label: str = "step",
               errors: list[str] | None = None) -> list[str]:
    """Collect every `ref:<name>` used by the step. Nested refs inside
    option lists/dicts are rejected — the runtime only substitutes
    top-level option values."""
    found: list[str] = []
    for k, v in (options or {}).items():
        if isinstance(v, str) and v.startswith("ref:"):
            found.append(v[4:])
        elif isinstance(v, (list, dict)):
            def _nested(x: Any) -> bool:
                if isinstance(x, str):
                    return x.startswith("ref:")
                if isinstance(x, dict):
                    return any(_nested(vv) for vv in x.values())
                if isinstance(x, list):
                    return any(_nested(vv) for vv in x)
                return False
            if _nested(v) and errors is not None:
                errors.append(f"{label}: option '{k}' nests a ref: inside a "
                              f"list/dict — refs only substitute as "
                              f"top-level option values")
    _expr_refs(anchor, found)
    _expr_refs(to, found)
    return found


def validate_scene(spec: dict, catalog_index: dict[str, dict],
                   *, max_duration: int = 20 * 60 * 5) -> SceneValidation:
    """Validate a scene spec (v2 grammar) against the catalog.

    `catalog_index` maps resource id -> catalog passport dict.
    Returns SceneValidation; `normalized` is set iff ok.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(spec, dict):
        return SceneValidation(ok=False, errors=["scene spec must be an object"])

    name = spec.get("name") or "scene"
    if not isinstance(name, str):
        errors.append("name must be a string")
        name = "scene"
    elif not re.fullmatch(r"[A-Za-z0-9](?!.*__)[A-Za-z0-9_\-]{0,63}", name):
        # frame-index parsing in SceneRun.finish() splits on '__' — keep
        # names strictly [A-Za-z0-9_-] so result keys stay unambiguous
        errors.append("name must match [A-Za-z0-9_-]{1,64} "
                      "(used in result keys and frame filenames)")
        name = "scene"
    scene_in = spec.get("scene") or {}
    if not isinstance(scene_in, dict):
        errors.append("scene must be an object {pos, time, weather}")
        scene_in = {}
    pos = scene_in.get("pos", [8.5, 2.0, 8.5])
    if not _vec3(pos):
        errors.append("scene.pos must be exactly [x, lift, z] numbers")
        pos = [8.5, 2.0, 8.5]
    else:
        pos = [float(c) for c in pos]
    try:
        time_v = int(scene_in.get("time", 6000))
    except (TypeError, ValueError):
        errors.append("scene.time must be a world-tick int (e.g. 6000)")
        time_v = 6000
    weather_v = scene_in.get("weather", "clear")
    if weather_v not in ("clear", "rain", "thunder"):
        warnings.append(f"scene.weather '{weather_v}' — known values: "
                        f"clear/rain/thunder (server will reject others)")
    scene = {
        "pos": pos,
        "time": time_v,
        "weather": str(weather_v),
    }

    cam_in = spec.get("camera") or {}
    if not isinstance(cam_in, dict):
        errors.append("camera must be an object {angles}")
        cam_in = {}
    angles = cam_in.get("angles") or spec.get("angles") or ["front"]
    if not isinstance(angles, list) or not angles:
        errors.append("camera.angles must be a non-empty list")
        angles = []
    else:
        seen_a: set[str] = set()
        deduped: list[str] = []
        for a in angles:
            if a not in KNOWN_ANGLES:
                errors.append(f"unknown camera angle '{a}' "
                              f"(known: {sorted(KNOWN_ANGLES)})")
            elif a in seen_a:
                warnings.append(f"camera.angles: '{a}' listed twice — "
                                f"kept once (a replay overwrites the "
                                f"first run's results)")
            else:
                seen_a.add(a)
                deduped.append(a)
        angles = deduped

    duration = spec.get("duration", 60)
    if not _is_int(duration) or duration <= 0 or duration > max_duration:
        errors.append(f"duration must be an int in 1..{max_duration}")
        duration = 60

    frames = spec.get("frames") or [3, 8, 20]
    if not isinstance(frames, list) or not all(
            _is_int(f) and f > 0 for f in frames):
        errors.append("frames must be a list of positive ints")
        frames = []
    else:
        kept: list[int] = []
        for f in frames:
            if f > duration:
                warnings.append(f"frame at tick {f} dropped — past "
                                f"duration {duration}")
            elif f in kept:
                warnings.append(f"frame at tick {f} listed twice — "
                                f"kept once")
            else:
                kept.append(f)
        frames = sorted(kept)
        if not frames:
            warnings.append("no frame ticks within duration — nothing will "
                            "be screenshotted")

    # ---- flatten groups into the step stream ---------------------------
    raw_steps: list[dict] = []
    for i, s in enumerate(spec.get("steps") or []):
        raw_steps.append((f"steps[{i}]", s, 0, None))
    for gi, g in enumerate(spec.get("groups") or []):
        glabel = f"groups[{gi}]"
        if not isinstance(g, dict):
            errors.append(f"{glabel}: must be an object")
            continue
        gtick = g.get("tick", 0)
        if not _is_int(gtick) or gtick < 0 or gtick >= duration:
            errors.append(f"{glabel}: tick must be an int in 0..{duration - 1}")
            continue
        grep = _validate_repeat(g.get("repeat"), glabel, duration,
                                errors, warnings, base_tick=gtick)
        if grep and "count" in grep and \
                gtick + (grep["count"] - 1) * grep["every"] >= duration:
            warnings.append(f"{glabel}: repeat tail exceeds duration "
                            f"— iterations past {duration} dropped")
        members = g.get("steps")
        if not isinstance(members, list) or not members:
            errors.append(f"{glabel}: steps must be a non-empty list")
            continue
        for mi, m in enumerate(members):
            raw_steps.append((f"{glabel}.steps[{mi}]", m, gtick, grep))

    if not raw_steps:
        errors.append("scene has no steps (steps[] and groups[].steps[] "
                      "are both empty)")

    # ---- pass 1: per-step field validation, collect names/ticks ---------
    norm_steps: list[dict] = []
    name_first_tick: dict[str, int] = {}
    deferred_ref_checks: list[tuple[dict, str, str]] = []  # (step, ref, label)

    def _one_step(label: str, s: Any, tick_shift: int,
                  group_repeat: dict | None) -> None:
        if not isinstance(s, dict):
            errors.append(f"{label}: must be an object")
            return
        STEP_KEYS = {"tick", "at_tick", "id", "name", "anchor", "at",
                     "offset", "direction", "distance", "pos", "to",
                     "follow", "track", "repeat", "options", "stop_after"}
        for k in s:
            if k not in STEP_KEYS:
                warnings.append(f"{label}: unknown key '{k}' — ignored")
        rid = s.get("id")
        tick = s.get("tick", s.get("at_tick", 0))
        if not _is_int(tick) or tick < 0:
            errors.append(f"{label}: tick must be an int >= 0")
            tick = 0
        tick += tick_shift
        if tick >= duration:
            errors.append(f"{label}: resolved tick {tick} >= duration "
                          f"{duration}")
            return
        if not isinstance(rid, str):
            errors.append(f"{label}: 'id' must be a resource id string")
            return
        res = catalog_index.get(rid)
        if res is None:
            errors.append(f"{label}: unknown resource '{rid}'")
            return
        kind = res.get("kind")
        if not res.get("ready_to_use"):
            errors.append(f"{label}: '{rid}' is not ready_to_use")
            return
        if kind not in SPAWNABLE_KINDS:
            reason = ("composite tuning bundles have no standalone spawn path"
                      if kind == "composite" else
                      f"kind '{kind}' is not spawnable in the scene lane")
            errors.append(f"{label}: '{rid}' — {reason}")
            return
        if kind == "world_event" and not res.get("factual", {}).get("has_visual"):
            errors.append(f"{label}: world_event '{rid}' has no visual output")
            return

        sname = s.get("name")
        if sname is not None and not isinstance(sname, str):
            errors.append(f"{label}: name must be a string")
            sname = None

        # anchor expr: either {"anchor": <expr>} or a shorthand string plus
        # top-level offset/direction/distance fields merged in
        anchor_expr = s.get("anchor")
        if anchor_expr is None and not any(
                k in s for k in ("offset", "direction", "distance")):
            anchor = None
        else:
            if isinstance(anchor_expr, str):
                anchor_expr = {"anchor": anchor_expr}
            elif anchor_expr is None:
                anchor_expr = {"anchor": "scene"}
            if isinstance(anchor_expr, dict):
                anchor_expr = dict(anchor_expr)
                for k in ("offset", "direction", "distance"):
                    if k in s and k not in anchor_expr:
                        anchor_expr[k] = s[k]
            anchor = _validate_anchor_expr(anchor_expr, label, "anchor", errors)
        to = _validate_anchor_expr(s.get("to"), label, "to", errors) \
            if "to" in s else None
        if to is not None and anchor and "direction" in anchor:
            warnings.append(f"{label}: 'to' is ignored when 'direction' is "
                            f"also set — the explicit direction wins")

        lpos = s.get("pos", [0.0, 0.0, 0.0])
        if not _vec3(lpos):
            errors.append(f"{label}: pos must be [dx,dy,dz] numbers")
            lpos = [0.0, 0.0, 0.0]

        follow = s.get("follow")
        if follow is True:
            follow = "player"
        if follow is not None and follow is not False:
            if follow not in FOLLOW_TARGETS:
                errors.append(f"{label}: follow '{follow}' — the probe world "
                              f"only has the player entity")
            elif kind not in PERSISTENT_KINDS:
                warnings.append(f"{label}: follow on instantaneous '{kind}' "
                                f"— spawn point resolves at its tick, "
                                f"nothing to steer afterwards")
            elif anchor is None or not anchor["anchor"].startswith("player"):
                warnings.append(f"{label}: follow re-resolves the anchor "
                                f"every tick — a non-player anchor "
                                f"({(anchor or {}).get('anchor')!r}) is "
                                f"constant, so follow changes nothing")
        if kind not in PERSISTENT_KINDS and (
                (to is not None and not (
                    anchor and ("offset" in anchor or "distance" in anchor)
                    or _vec3(lpos) and any(c != 0 for c in lpos)))
                or (anchor and "direction" in anchor and "offset" not in
                    anchor and "distance" not in anchor and to is None)):
            warnings.append(f"{label}: 'to'/'direction' on instantaneous "
                            f"'{kind}' only rotates the offset frame — with "
                            f"no offset/distance it changes nothing at all")

        track = _validate_track(s.get("track"), label, kind, errors, warnings)
        if track and "rotation" in track and (to is not None or (
                anchor and "direction" in anchor)):
            warnings.append(f"{label}: track.rotation overrides the facing "
                            f"each tick — 'to'/'direction' aim is lost")

        options = s.get("options") or {}
        if not isinstance(options, dict):
            errors.append(f"{label}: options must be an object")
            options = {}

        pschema = res.get("parameter_schema") or {}
        effective = dict(PARAM_SPECS.get(rid, {}))
        effective.update(options)
        for sk in pschema:
            _check_param(sk, pschema, effective, f"{label} '{rid}'", errors)

        rep = _validate_repeat(s.get("repeat"), label, duration, errors,
                               warnings, base_tick=tick + tick_shift) \
            if "repeat" in s else None
        if rep and "count" in rep and \
                tick + (rep["count"] - 1) * rep["every"] >= duration:
            warnings.append(f"{label}: repeat tail exceeds duration — "
                            f"iterations past {duration} are dropped")

        step_refs = _ref_names(options, anchor, to, label, errors)

        vs = res.get("visual_status")
        vsr = res.get("visual_status_reason")
        if vs == "environment_mismatch":
            warnings.append(f"{label}: '{rid}' {vs}:{vsr} — the dry air scene "
                            f"will most likely show nothing")
        elif vs == "capture_failed":
            warnings.append(f"{label}: '{rid}' {vs}:{vsr} — catalog capture "
                            f"placed it offscreen; check the framing")

        step = {
            "at_tick": tick,
            "name": sname,
            "id": rid,
            "kind": kind,
            "at": anchor,
            "to": to,
            "pos": [float(c) for c in lpos],
            "follow": follow or None,
            "track": track,
            "repeat": rep,
            "group_repeat": group_repeat,
            "group_tick": tick_shift if group_repeat else None,
            "options": options,
            "stop_after": _stop_after(s, label, warnings),
        }
        for ref in step_refs:
            deferred_ref_checks.append((step, ref, label))
        norm_steps.append(step)
        if sname and sname not in name_first_tick:
            name_first_tick[sname] = tick

    for label, s, shift, grep in raw_steps:
        _one_step(label, s, shift, grep)

    # ---- pass 2: name uniqueness + ref ordering --------------------------
    seen: dict[str, int] = {}
    for st in norm_steps:
        if st["name"]:
            if st["name"] in seen:
                warnings.append(f"ref target '{st['name']}' has multiple "
                                f"firings — refs resolve to the most "
                                f"recent spawn before the consumer")
            else:
                seen[st["name"]] = st["at_tick"]

    # ---- tick-scheduled server commands (e.g. move the player) ----------
    commands: list[dict] = []
    for i, c in enumerate(spec.get("commands") or []):
        label = f"commands[{i}]"
        if not isinstance(c, dict) or not isinstance(c.get("command"), str):
            errors.append(f"{label}: must be " + "{'tick': int, 'command': str}")
            continue
        ctick = c.get("tick", 0)
        if not _is_int(ctick) or ctick < 0 or ctick >= duration:
            errors.append(f"{label}: tick must be an int in 0..{duration - 1}")
            continue
        commands.append({"at_tick": ctick, "command": c["command"]})

    norm_steps.sort(key=lambda x: x["at_tick"])
    # final ordering decides ref legality: the producer's first instance must
    # precede the consumer in the sorted stream (runtime spawns in order).
    # index by identity — two identical step dicts would collide on .index()
    step_pos = {id(st): i for i, st in enumerate(norm_steps)}
    producer_order: dict[str, int] = {}
    for idx, st in enumerate(norm_steps):
        if st["name"] and st["name"] not in producer_order:
            producer_order[st["name"]] = idx
    for consumer, ref, label in deferred_ref_checks:
        if ref not in producer_order:
            errors.append(f"{label}: 'ref:{ref}' names no step")
            continue
        if producer_order[ref] >= step_pos[id(consumer)]:
            errors.append(
                f"{label}: 'ref:{ref}' resolves to a step that spawns after "
                f"this one (tick {name_first_tick[ref]})")
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
            "steps": norm_steps,
            "commands": commands,
        })
