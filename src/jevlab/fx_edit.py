"""Narrow Photon .fx customization layer.

Implements the semantic ops the editor-need research actually demanded:
inspect / clone / patch (scalar | color | toggle only) / validate / register.

NOT a graph editor: no node add/remove/reconnect, no curve editing, no
texture or material swaps, no arbitrary NBT paths. Paths are semantic
(`emission.bursts[0].count`, `color`, `lights`, `emitter:0`), resolved
against the real Photon NBT layout:

    root { fxData: { fxObjects: [ {type, data:{name,transform,config}} ] },
           version }

- `data.config.<field>` where a field is either a plain scalar tag
  (`duration: int`), an enum string (`simulationSpace: str`), or a
  NumberFunction wrapper `{type: constant|color|gradient|..., data: {...}}`.
- Optional sub-features live in compounds that carry `_enable: byte`
  (`lights`, `trails`, `uvAnimation`, `physics`, ...): the layer toggle.
- Whole-emitter disable removes the fxObject entry (scrubbing
  `_childrenId` references) — the only data-level channel Photon gives.

Round-trip fidelity: jevlab.fx_nbt decode→encode is byte-identical on all
stock vfxlab fixtures, so patching never rewrites untouched bytes beyond
the gzip header.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import Any

from .fx_nbt import (Tag, TAG_BYTE, TAG_BYTE_ARRAY, TAG_COMPOUND, TAG_DOUBLE,
                     TAG_FLOAT, TAG_INT, TAG_INT_ARRAY, TAG_LIST,
                     TAG_LONG, TAG_LONG_ARRAY, TAG_SHORT, TAG_STRING,
                     load_fx, save_fx)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FX_SRC_DIR = os.path.join(REPO, "probe/src/main/resources/assets")
# LDLib2 hidden-pack assets dir; FXHelper resolves fx ids from here at
# runtime even before a gradle re-run (FixtureGenScenario uses the same
# path for the stock fixtures).
FX_RUNTIME_DIR = os.path.join(REPO, "probe/run/ldlib2/assets")
CATALOG = os.path.join(REPO, "data/catalog.json")
PROVENANCE_DIR = os.path.join(REPO, "data/fx_provenance")

FX_OBJECT_TYPES = {
    "beam_emitter", "particle_emitter", "trail_emitter",
    "ara_trail_emitter", "empty",
}
NUMBER_FUNCTION_TYPES = {
    "constant", "random_constant", "color", "gradient", "random_color",
    "random_gradient", "curve", "random_curve",
}
_ID_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")


# ---------------------------------------------------------------- paths

def fx_file_path(resource_id: str, root: str | None = None) -> str:
    if root is None:
        root = FX_SRC_DIR
    ns, _, name = resource_id.partition(":")
    return os.path.join(root, ns, "fx", name + ".fx")


def resolve_fx_file(resource_id: str) -> str | None:
    """Locate the .fx backing a catalog/registered id."""
    for root in (FX_SRC_DIR, FX_RUNTIME_DIR):
        p = fx_file_path(resource_id, root)
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------- helpers

def _is_numfunc(tag: Tag) -> bool:
    return (tag.type == TAG_COMPOUND and tag.get("type") is not None
            and tag.get("type").type == TAG_STRING
            and tag.get("type").value in NUMBER_FUNCTION_TYPES)


def _nf_constant_value(tag: Tag):
    """(value, number_tag) for a constant NumberFunction, else None."""
    if not _is_numfunc(tag) or tag.get("type").value != "constant":
        return None
    data = tag.get("data")
    if data is None or data.type != TAG_COMPOUND:
        return None
    num = data.get("number")
    if num is None or num.type not in (TAG_BYTE, TAG_SHORT, TAG_INT,
                                       TAG_LONG, TAG_FLOAT, TAG_DOUBLE):
        return None
    return num.value, num


def _nf_color_value(tag: Tag) -> int | None:
    if not _is_numfunc(tag) or tag.get("type").value != "color":
        return None
    num = tag.get("data") and tag.get("data").get("number")
    return num.value if num and num.type == TAG_INT else None


def _hex_argb(v: int) -> str:
    return f"#{(v & 0xFFFFFFFF):08x}"


def _objects(root: Tag) -> Tag:
    objs = root.get("fxData")
    if objs is None or objs.get("fxObjects") is None:
        raise ValueError("not a Photon .fx (no fxData.fxObjects)")
    return objs.get("fxObjects")


def _resolve_emitter(objs: Tag, sel: str) -> tuple[int, Tag]:
    """sel = index or emitter name."""
    if sel.isdigit():
        i = int(sel)
        if not (0 <= i < len(objs.value)):
            raise IndexError(f"emitter index {i} out of range "
                             f"({len(objs.value)} objects)")
        return i, objs.value[i]
    for i, o in enumerate(objs.value):
        name = o.get("data") and o.get("data").get("name")
        if name and name.value == sel:
            return i, o
    raise KeyError(f"no emitter named '{sel}'")


# ---------------------------------------------------------------- inspect

def _describe_field(tag: Tag) -> dict[str, Any]:
    if _is_numfunc(tag):
        nt = tag.get("type").value
        out: dict[str, Any] = {"kind": "number_function", "type": nt}
        if nt == "constant":
            cf = _nf_constant_value(tag)
            out["value"] = cf[0] if cf else None
            out["patchable"] = "scalar"
        elif nt == "color":
            v = _nf_color_value(tag)
            out["value"] = _hex_argb(v) if v is not None else None
            out["patchable"] = "color"
        else:
            out["patchable"] = None
            out["note"] = f"{nt} is not a plain constant — not patchable"
        return out
    if tag.type == TAG_LIST and all(v.type == TAG_FLOAT for v in tag.value):
        return {"kind": "vec", "value": [v.value for v in tag.value],
                "patchable": "scalar"}
    if tag.type in (TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG, TAG_FLOAT,
                    TAG_DOUBLE):
        return {"kind": "scalar", "value": tag.value, "patchable": "scalar"}
    if tag.type == TAG_STRING:
        return {"kind": "enum", "value": tag.value, "patchable": "scalar"}
    if tag.type == TAG_COMPOUND:
        keys = tag.keys()
        out = {"kind": "group", "fields": {}}
        if "_enable" in keys:
            out["enabled"] = bool(tag.get("_enable").value)
            out["patchable"] = "toggle"
        return out
    return {"kind": f"tag{tag.type}", "patchable": None}


def _walk_config(comp: Tag, prefix: str, out: dict[str, Any],
                 depth: int = 0) -> None:
    """Flatten a config compound into semantic-path descriptions."""
    for name, tag in comp.value:
        if name.startswith("_"):
            continue
        path = f"{prefix}.{name}" if prefix else name
        desc = _describe_field(tag)
        if desc["kind"] == "group" and depth < 2:
            if "enabled" in desc:
                out[path] = {**desc, "kind": "layer"}
            _walk_config(tag, path, out, depth + 1)
        elif (tag.type == TAG_LIST and tag.value
                and all(v.type == TAG_COMPOUND for v in tag.value)
                and depth < 3):
            for i, v in enumerate(tag.value):
                _walk_config(v, f"{path}[{i}]", out, depth + 1)
        else:
            out[path] = desc


def inspect_fx(resource_id: str) -> dict[str, Any]:
    """Normalized, agent-friendly view of an .fx resource."""
    path = resolve_fx_file(resource_id)
    if path is None:
        return {"ok": False, "error": f"no .fx file for '{resource_id}'"}
    name, root = load_fx(path)
    try:
        objs = _objects(root)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    emitters = []
    for i, o in enumerate(objs.value):
        data = o.get("data")
        etype = o.get("type").value if o.get("type") else "?"
        entry: dict[str, Any] = {
            "index": i,
            "type": etype,
            "name": data.get("name").value if data.get("name") else f"obj{i}",
            "fields": {},
            "layers": {},
        }
        if data and data.get("config"):
            flat: dict[str, Any] = {}
            _walk_config(data.get("config"), "", flat)
            for p, d in flat.items():
                if d.get("kind") == "layer":
                    entry["layers"][p] = {"enabled": d["enabled"],
                                          "patchable": "toggle"}
                elif d.get("patchable") in ("scalar", "color"):
                    entry["fields"][p] = d
        emitters.append(entry)

    return {
        "ok": True,
        "id": resource_id,
        "file": os.path.relpath(path, REPO),
        "version": (root.get("version").value if root.get("version") else None),
        "emitters": emitters,
        "ops": {
            "scalar": "patch scalar <emitter>.<field> = value "
                      "(number/int/float, or [x,y,z] for vec fields)",
            "color": "patch color <emitter>.<field> = #RRGGBB "
                     "(fields with type 'color')",
            "toggle": "patch toggle <emitter>.<layer> = on|off, or "
                      "patch toggle emitter:<index|name> = off",
        },
        "note": "only scalar/color/toggle fields are patchable; "
                "gradient/curve/random number functions are not",
    }


# ---------------------------------------------------------------- clone

def _new_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


def clone_fx(source_id: str, new_id: str,
             ops: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Clone an .fx to a new id (original never touched), optionally patch."""
    if not _ID_RE.match(new_id):
        return {"ok": False, "error": f"bad resource id '{new_id}'"}
    src = resolve_fx_file(source_id)
    if src is None:
        return {"ok": False, "error": f"no .fx file for '{source_id}'"}
    dst = fx_file_path(new_id)
    if resolve_fx_file(new_id):
        return {"ok": False, "error": f"'{new_id}' already exists"}

    name, root = load_fx(src)
    # fresh object ids + names so runtime dedup never collides
    objs = _objects(root)
    for o in objs.value:
        data = o.get("data")
        tr = data.get("transform") if data else None
        if tr and tr.get("id") and tr.get("id").type == TAG_STRING:
            tr.get("id").value = _new_uuid()

    applied, errors = ([], [])
    if ops:
        applied, errors = apply_ops(root, ops)
        if errors:
            return {"ok": False, "error": "patch failed, clone not written",
                    "errors": errors}

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    save_fx(dst, name, root)
    # runtime hidden-pack copy so the current dev client resolves it
    rt = fx_file_path(new_id, FX_RUNTIME_DIR)
    try:
        os.makedirs(os.path.dirname(rt), exist_ok=True)
        shutil.copyfile(dst, rt)
    except OSError:
        rt = None

    prov = {"source": source_id, "cloned_at": time.time(),
            "ops": ops or []}
    os.makedirs(PROVENANCE_DIR, exist_ok=True)
    with open(os.path.join(PROVENANCE_DIR,
                           new_id.replace(":", "_") + ".json"), "w") as f:
        json.dump(prov, f, indent=2)

    return {"ok": True, "id": new_id,
            "file": os.path.relpath(dst, REPO),
            "runtime_copy": os.path.relpath(rt, REPO) if rt else None,
            "applied_ops": applied,
            "next": "call fx_register to expose it to find/scene/play"}


# ---------------------------------------------------------------- patch

_SETTABLE_SCALAR_TAGS = (TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG,
                         TAG_FLOAT, TAG_DOUBLE, TAG_STRING)


def _set_scalar_field(tag: Tag, value: Any, path: str) -> str:
    nf = _nf_constant_value(tag)
    if nf is not None:
        num = nf[1]
        if not isinstance(value, (int, float)):
            raise TypeError(f"{path}: expected number, got {value!r}")
        num.value = int(value) if num.type in (
            TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG) else float(value)
        return f"{path}: constant -> {num.value}"
    if tag.type == TAG_LIST and all(v.type == TAG_FLOAT
                                    for v in tag.value):
        if not (isinstance(value, list) and len(value) == len(tag.value)):
            raise TypeError(f"{path}: expected list len {len(tag.value)}")
        for v, x in zip(tag.value, value):
            v.value = float(x)
        return f"{path}: vec -> {value}"
    if tag.type == TAG_STRING:
        if not isinstance(value, str):
            raise TypeError(f"{path}: expected string")
        tag.value = value
        return f"{path}: '{value}'"
    if tag.type in (TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG):
        tag.value = int(value)
        return f"{path}: -> {tag.value}"
    if tag.type in (TAG_FLOAT, TAG_DOUBLE):
        tag.value = float(value)
        return f"{path}: -> {tag.value}"
    raise TypeError(f"{path}: field of tag type {tag.type} "
                    "is not scalar-patchable")


def _set_color_field(tag: Tag, value: str, path: str) -> str:
    if _nf_color_value(tag) is None:
        raise TypeError(f"{path}: not a constant color field "
                        f"(type={tag.get('type').value if _is_numfunc(tag) else tag.type})")
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", value)
    if not m:
        raise TypeError(f"{path}: expected #RRGGBB, got {value!r}")
    rgb, a = int(m.group(1), 16), m.group(2)
    argb = ((int(a, 16) << 24) | rgb) if a else (0xFF000000 | rgb)
    if argb >= 0x80000000:
        argb -= 0x100000000
    tag.get("data").get("number").value = argb
    return f"{path}: color -> {_hex_argb(argb)}"


def _dig(parent: Tag, path: str) -> Tag:
    """path a.b[0].c within an emitter's config."""
    cur = parent
    for part in path.split("."):
        m = re.fullmatch(r"([A-Za-z_0-9]+)(\[(\d+)\])?", part)
        if not m:
            raise KeyError(f"bad path segment '{part}'")
        key, idx = m.group(1), m.group(3)
        cur = cur.get(key) if cur.type == TAG_COMPOUND else None
        if cur is None:
            raise KeyError(f"no field '{key}'")
        if idx is not None:
            i = int(idx)
            if cur.type != TAG_LIST or i >= len(cur.value):
                raise KeyError(f"'{key}[{i}]' not a list slot")
            cur = cur.value[i]
    return cur


def apply_ops(root: Tag, ops: list[dict[str, Any]]) -> tuple[list, list]:
    """Apply semantic patch ops to a decoded root. Returns (applied, errors)."""
    objs = _objects(root)
    applied, errors = [], []
    for op in ops:
        kind = op.get("op")
        target = op.get("emitter", "0")
        try:
            if kind == "toggle" and str(target).startswith("emitter"):
                sel = str(target).split(":", 1)[1] if ":" in str(target) \
                    else str(target)
                idx, _ = _resolve_emitter(objs, sel)
                if op.get("value") in (False, "off", 0):
                    if len(objs.value) <= 1:
                        raise ValueError("cannot disable the only emitter")
                    oid = (objs.value[idx].get("data").get("transform")
                           .get("id").value)
                    del objs.value[idx]
                    # scrub dangling references
                    for o in objs.value:
                        d = o.get("data")
                        if not d:
                            continue
                        tr = d.get("transform")
                        if not tr:
                            continue
                        ch = tr.get("_childrenId")
                        if ch and ch.type == TAG_LIST:
                            ch.value = [c for c in ch.value
                                        if c.value != oid]
                        par = tr.get("_parentId")
                        if par and par.type == TAG_STRING \
                                and par.value == oid:
                            par.value = "_NULL_"
                    applied.append(f"emitter:{sel} removed")
                else:
                    raise ValueError("re-enabling a removed emitter is not "
                                     "supported — re-clone instead")
                continue

            idx, obj = _resolve_emitter(objs, str(target))
            data = obj.get("data")
            cfg = data.get("config") if data else None
            if cfg is None:
                raise KeyError("emitter has no config")

            if kind == "scalar":
                field = _dig(cfg, op["field"])
                applied.append(_set_scalar_field(field, op["value"],
                                                 f"{target}.{op['field']}"))
            elif kind == "color":
                field = _dig(cfg, op["field"])
                applied.append(_set_color_field(field, op["value"],
                                                f"{target}.{op['field']}"))
            elif kind == "toggle":
                comp = _dig(cfg, op["field"])
                if comp.type != TAG_COMPOUND or comp.get("_enable") is None:
                    raise TypeError(
                        f"{target}.{op['field']}: not a toggleable layer "
                        "(no _enable flag)")
                on = op.get("value") in (True, "on", 1)
                comp.get("_enable").value = 1 if on else 0
                applied.append(
                    f"{target}.{op['field']}: _enable -> {1 if on else 0}")
            else:
                raise ValueError(f"unknown op '{kind}' "
                                 "(use scalar|color|toggle)")
        except (KeyError, IndexError, TypeError, ValueError) as e:
            errors.append(f"op {op}: {e}")
    return applied, errors


def patch_fx(resource_id: str, ops: list[dict[str, Any]]) -> dict[str, Any]:
    """Patch an already-cloned .fx in place (both src + runtime copies)."""
    path = fx_file_path(resource_id)
    if not os.path.exists(path):
        alt = resolve_fx_file(resource_id)
        if alt is None:
            return {"ok": False, "error": f"no .fx file for '{resource_id}'"}
        path = alt
    name, root = load_fx(path)
    applied, errors = apply_ops(root, ops)
    if errors:
        return {"ok": False, "applied": applied, "errors": errors}
    save_fx(path, name, root)
    rt = fx_file_path(resource_id, FX_RUNTIME_DIR)
    if os.path.exists(rt):
        try:
            shutil.copyfile(path, rt)
        except OSError:
            pass
    prov_path = os.path.join(PROVENANCE_DIR,
                             resource_id.replace(":", "_") + ".json")
    if os.path.exists(prov_path):
        prov = json.load(open(prov_path))
        prov.setdefault("ops", []).extend(ops)
        json.dump(prov, open(prov_path, "w"), indent=2)
    return {"ok": True, "applied": applied,
            "file": os.path.relpath(path, REPO)}


# ---------------------------------------------------------------- validate

def validate_fx(resource_id: str) -> dict[str, Any]:
    """Structural validation: readable, well-formed, known types."""
    path = resolve_fx_file(resource_id)
    if path is None:
        return {"ok": False, "errors": [f"no .fx file for '{resource_id}'"],
                "warnings": []}
    errors, warnings = [], []
    try:
        name, root = load_fx(path)
    except Exception as e:
        return {"ok": False, "errors": [f"unreadable NBT: {e}"],
                "warnings": []}
    if name not in ("", "fxData"):
        warnings.append(f"root name '{name}'")
    try:
        objs = _objects(root)
    except ValueError as e:
        errors.append(str(e))
        return {"ok": False, "errors": errors, "warnings": warnings}
    if not objs.value:
        warnings.append("empty fxObjects — effect will render nothing")
    seen_ids = set()
    for i, o in enumerate(objs.value):
        lab = f"fxObjects[{i}]"
        ot = o.get("type")
        if ot is None or ot.value not in FX_OBJECT_TYPES:
            errors.append(f"{lab}: unknown object type "
                          f"'{ot.value if ot else None}'")
        data = o.get("data")
        if data is None or data.type != TAG_COMPOUND:
            errors.append(f"{lab}: missing data compound")
            continue
        tr = data.get("transform")
        if tr is None or tr.get("id") is None:
            errors.append(f"{lab}: no transform.id")
        else:
            oid = tr.get("id").value
            if oid in seen_ids:
                warnings.append(f"{lab}: duplicate object id {oid}")
            seen_ids.add(oid)
        cfg = data.get("config")
        if cfg is None:
            errors.append(f"{lab}: no config")
        else:
            for k, t in cfg.value:
                if _is_numfunc(t):
                    continue
                if t.type == TAG_COMPOUND:
                    for k2, t2 in t.value:
                        if (_is_numfunc(t2) and t2.get("type").value
                                not in NUMBER_FUNCTION_TYPES):
                            warnings.append(
                                f"{lab}.{k}.{k2}: odd numfunc type")
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "emitters": len(objs.value)}


# ---------------------------------------------------------------- register

def register_fx(resource_id: str, source_id: str | None = None) -> dict[str, Any]:
    """Make a cloned .fx a first-class catalog resource."""
    cat = json.load(open(CATALOG))
    resources = cat["resources"]
    if any(r["id"] == resource_id for r in resources):
        return {"ok": False, "error": f"'{resource_id}' already in catalog"}

    v = validate_fx(resource_id)
    if not v["ok"]:
        return {"ok": False, "error": "validation failed",
                "validation": v}

    prov_path = os.path.join(PROVENANCE_DIR,
                             resource_id.replace(":", "_") + ".json")
    prov = (json.load(open(prov_path)) if os.path.exists(prov_path)
            else {"source": source_id or "unknown", "ops": []})
    src_id = prov["source"]
    src = next((r for r in resources if r["id"] == src_id), None)

    ns, _, name = resource_id.partition(":")
    passport: dict[str, Any] = {
        "schema_version": 1,
        "id": resource_id,
        "source": "fx-edit",
        "namespace": ns,
        "kind": "fx",
        "ready_to_use": True,
        "primitive": False,
        "parameterized": False,
        "factual": dict(src.get("factual", {})) if src else
                   {"container": "photon_fx", "format": "gzipped NBT"},
        "provenance": [{
            "kind": "fx_clone",
            "producer": "jevlab.fx_edit",
            "at": prov.get("cloned_at", time.time()),
            "detail": f"source={src_id} ops={json.dumps(prov.get('ops', []))}",
        }],
        "diagnostics": [
            f"clone of {src_id}; measured/visual data inherited from the "
            "source passport — re-capture pending; patches applied: "
            f"{len(prov.get('ops', []))}",
        ],
    }
    if src:
        for key in ("measured", "visual", "visual_status",
                    "visual_status_reason", "possible_roles", "capabilities"):
            if src.get(key):
                passport[key] = src[key]
        # inherited visuals describe the SOURCE look; flag it
        if src.get("visual_status") == "observed":
            passport["visual_status_reason"] = (
                "inherited from source clone; re-capture pending")

    resources.append(passport)
    cat.setdefault("diagnostics", []).append(
        f"{time.strftime('%Y-%m-%d')}: registered {resource_id} "
        f"(clone of {src_id})")
    with open(CATALOG, "w") as f:
        json.dump(cat, f)

    return {"ok": True, "id": resource_id,
            "source": src_id,
            "catalog": os.path.relpath(CATALOG, REPO),
            "ready_to_use": True,
            "next": "usable via vfx_find/vfx_inspect/vfx_scene_* "
                    "and spawn kind 'fx'"}
