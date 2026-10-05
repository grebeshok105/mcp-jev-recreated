"""Narrow Photon .fx customization layer.

Implements the semantic ops the editor-need research actually demanded:
inspect / clone / patch (scalar | color | toggle only) / validate / register.

NOT a graph editor: no node add/remove/reconnect, no curve editing, no
texture or material swaps, no arbitrary NBT paths. Paths are semantic
(`emission.bursts.payload[0].count`, `color`, `lights`, `emitter:0`),
resolved against the real Photon NBT layout:

    root { version, fxData: { fxObjects: [ {type, data:{name,transform,
                                                       config}} ] } }

- `data.config.<field>` where a field is either a plain scalar tag
  (`duration: int`), an enum string (`simulationSpace: str`), or a
  NumberFunction wrapper `{type: constant|color|gradient|..., data: {...}}`.
- Optional sub-features live in compounds that carry `_enable: byte`
  (`lights`, `trails`, `uvAnimation`, `physics`, ...): the layer toggle.
- Whole-emitter disable removes the fxObject entry and scrubs every
  reference to its transform id (`_parentId`, `_childrenId`, uuid strings
  in configs such as TransformRef fields).

Safety contract:
- Originals are never mutated: patch_fx refuses ids without a provenance
  file (i.e. anything that did not come through clone_fx) unless the
  caller passes allow_stock=True.
- Ops touch only semantic fields: numfunc interiors (`*.data.*`), `_`-keys
  and transform ids are refused — report, never guess.
- Writes are atomic: payload is fully encoded before the target file is
  truncated (tmp + os.replace), for .fx, provenance and catalog alike.

Round-trip fidelity: jevlab.fx_nbt decode→encode is byte-identical on all
stock vfxlab fixtures, so patching never rewrites untouched bytes beyond
the gzip header. Edge: MUTF-8 strings (NUL / non-BMP) and empty typed
lists are decoded faithfully but encode may differ from Java — the codec
fails loud rather than corrupting.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import struct
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
# ns:name; name may be a nested fx path (fx/sub/name.fx). ".." segments and
# leading "/" are rejected separately — Photon paths never contain them.
_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+:[a-zA-Z0-9_./-]+$")
_EMITTER_SEL_RE = re.compile(r"^emitter:(\d+|.+)$")

_INT_RANGES = {
    TAG_BYTE: (-0x80, 0x7F),
    TAG_SHORT: (-0x8000, 0x7FFF),
    TAG_INT: (-0x80000000, 0x7FFFFFFF),
    TAG_LONG: (-0x8000000000000000, 0x7FFFFFFFFFFFFFFF),
}

# Whitelisted enum domains for known string fields, matched on the last
# path segment. Values verified against Photon sources
# (ParticleConfig.Space, EmissionSetting.Mode, RendererSetting.Layer/SortMode).
_ENUM_DOMAINS = {
    "simulationSpace": {"Local", "World"},
    "emissionMode": {"Exacting", "Random"},
    "layer": {"Opaque", "Translucent"},
    "sortMode": {"NONE", "DISTANCE"},
}

# Numeric bounds for known scalar fields, matched on the last path segment.
# interval=0 hits `realAge % interval` ArithmeticException at runtime;
# probability outside 0..1 silently never/exactly fires; negative
# duration/count values are meaningless to Photon.
_FIELD_BOUNDS: dict[str, tuple[float, float]] = {
    "duration": (0, float("inf")),
    "maxParticles": (0, float("inf")),
    "startDelay": (0, float("inf")),
    "prewarm": (0, float("inf")),
    "emissionRate": (0, float("inf")),
    "distanceRate": (0, float("inf")),
    "minVertexDistance": (0, float("inf")),
    "count": (0, float("inf")),
    "time": (0, float("inf")),
    "probability": (0.0, 1.0),
    "cycles": (1, float("inf")),
    "interval": (1, float("inf")),
}


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


def _valid_id(resource_id: str) -> bool:
    if not _ID_RE.match(resource_id):
        return False
    name = resource_id.split(":", 1)[1]
    return all(seg not in ("", "..") for seg in name.split("/")) \
        and not name.endswith("..")


def _prov_path(resource_id: str, legacy_ok: bool = True) -> str:
    """Provenance file for an id. `<slug>-<sha8>.json` is collision-proof
    (a:b_c vs a_b:c map to distinct slugs). `legacy_ok` also finds files
    written by the pre-hash scheme `ns_name.json`."""
    slug = re.sub(r"[^a-zA-Z0-9_.-]", "_", resource_id)
    p = os.path.join(PROVENANCE_DIR,
                     f"{slug}-{hashlib.sha1(resource_id.encode()).hexdigest()[:8]}.json")
    if legacy_ok and not os.path.exists(p):
        legacy = os.path.join(
            PROVENANCE_DIR, resource_id.replace(":", "_") + ".json")
        if os.path.exists(legacy):
            return legacy
    return p


def _atomic_write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _atomic_write_json(path: str, obj: Any) -> None:
    _atomic_write(path, json.dumps(obj, ensure_ascii=False,
                                   indent=2).encode("utf-8"))


# ---------------------------------------------------------------- helpers

def _is_numfunc(tag: Tag) -> bool:
    return (tag.type == TAG_COMPOUND and tag.get("type") is not None
            and tag.get("type").type == TAG_STRING
            and tag.get("type").value in NUMBER_FUNCTION_TYPES)


def _numfunc_shaped(tag: Tag) -> bool:
    """Looks like a number-function wrapper even when the type name is
    unknown — `{type: <str>, data: <compound>}`."""
    return (tag.type == TAG_COMPOUND
            and tag.get("type") is not None
            and tag.get("type").type == TAG_STRING
            and tag.get("data") is not None
            and tag.get("data").type == TAG_COMPOUND)


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
    fx = root.get("fxData")
    if fx is None or fx.type != TAG_COMPOUND:
        raise ValueError("not a Photon .fx (no fxData compound)")
    objs = fx.get("fxObjects")
    if objs is None:
        raise ValueError("not a Photon .fx (no fxData.fxObjects)")
    if objs.type != TAG_LIST:
        raise ValueError("fxData.fxObjects is not a list")
    return objs


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


def _walk_tag_strings(tag: Tag, fn) -> None:
    """Apply fn(name, tag) to every TAG_STRING inside compounds/lists,
    recursively — covers transform ids and config TransformRef fields."""
    if tag.type == TAG_COMPOUND:
        for name, t in tag.value:
            if t.type == TAG_STRING:
                fn(t)
            else:
                _walk_tag_strings(t, fn)
    elif tag.type == TAG_LIST:
        for t in tag.value:
            _walk_tag_strings(t, fn)


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
    if tag.type == TAG_LIST:
        if tag.value and all(v.type == TAG_FLOAT for v in tag.value):
            return {"kind": "vec", "value": [v.value for v in tag.value],
                    "patchable": "scalar"}
        return {"kind": "list", "patchable": None}
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
    try:
        name, root = load_fx(path)
        objs = _objects(root)
    except Exception as e:
        return {"ok": False, "error": f"unreadable .fx: {e}"}

    emitters = []
    for i, o in enumerate(objs.value):
        data = o.get("data") if o.type == TAG_COMPOUND else None
        etype = o.get("type").value if o.get("type") else "?"
        name_t = data.get("name") if data else None
        entry: dict[str, Any] = {
            "index": i,
            "type": etype,
            "name": (name_t.value if name_t and name_t.type == TAG_STRING
                     else f"obj{i}"),
            "fields": {},
            "layers": {},
        }
        cfg = data.get("config") if data else None
        if cfg is not None and cfg.type == TAG_COMPOUND:
            flat: dict[str, Any] = {}
            _walk_config(cfg, "", flat)
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
            "color": "patch color <emitter>.<field> = #RRGGBB|#AARRGGBB "
                     "(fields with type 'color')",
            "toggle": "patch toggle <emitter>.<layer> = on|off, or "
                      "patch toggle emitter:<index|name> = off",
        },
        "note": "only scalar/color/toggle fields are patchable; "
                "gradient/curve/random number functions are not. "
                "inspect shows paths to bounded depth — deeper fields "
                "still accept ops when addressed directly",
    }


# ---------------------------------------------------------------- clone

def _new_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


def _remap_transform_ids(root: Tag) -> None:
    """Give every fxObject a fresh transform.id AND remap every reference
    (transform._parentId/_childrenId, uuid strings in configs such as
    TransformRef fields). Without the remap a multi-emitter clone keeps
    pointing at the source's ids and the hierarchy silently flattens."""
    objs = _objects(root)
    id_map: dict[str, str] = {}
    for o in objs.value:
        data = o.get("data") if o.type == TAG_COMPOUND else None
        tr = data.get("transform") if data else None
        if tr and tr.get("id") and tr.get("id").type == TAG_STRING:
            old = tr.get("id").value
            new = _new_uuid()
            id_map[old] = new
            tr.get("id").value = new
    if not id_map:
        return

    def remap(t: Tag) -> None:
        if t.value in id_map:
            t.value = id_map[t.value]

    for o in objs.value:
        data = o.get("data") if o.type == TAG_COMPOUND else None
        if data is None:
            continue
        tr = data.get("transform")
        if tr:
            ch = tr.get("_childrenId")
            if ch and ch.type == TAG_LIST:
                for c in ch.value:
                    remap(c)
            par = tr.get("_parentId")
            if par and par.type == TAG_STRING:
                remap(par)
        cfg = data.get("config")
        if cfg:
            _walk_tag_strings(cfg, remap)


def clone_fx(source_id: str, new_id: str,
             ops: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Clone an .fx to a new id (original never touched), optionally patch."""
    if not _valid_id(new_id):
        return {"ok": False, "error": f"bad resource id '{new_id}'"}
    src = resolve_fx_file(source_id)
    if src is None:
        return {"ok": False, "error": f"no .fx file for '{source_id}'"}
    dst = fx_file_path(new_id)
    if resolve_fx_file(new_id):
        return {"ok": False, "error": f"'{new_id}' already exists"}

    try:
        name, root = load_fx(src)
        _objects(root)
    except Exception as e:
        return {"ok": False, "error": f"unreadable source .fx: {e}"}
    _remap_transform_ids(root)

    applied, errors = ([], [])
    if ops:
        applied, errors = apply_ops(root, ops)
        if errors:
            return {"ok": False, "error": "patch failed, clone not written",
                    "errors": errors}

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        save_fx(dst, name, root)
    except (OSError, ValueError, struct.error) as e:
        return {"ok": False, "error": f"encode failed: {e}"}
    # runtime hidden-pack copy so the current dev client resolves it
    rt = fx_file_path(new_id, FX_RUNTIME_DIR)
    try:
        os.makedirs(os.path.dirname(rt), exist_ok=True)
        shutil.copyfile(dst, rt)
    except OSError:
        rt = None

    try:
        with open(src, "rb") as f:
            src_hash = hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        src_hash = None
    prov = {"source": source_id, "source_sha256": src_hash,
            "cloned_at": time.time(), "ops": ops or [],
            "ops_history": [{"at": time.time(), "ops": ops or []}]}
    try:
        _atomic_write_json(_prov_path(new_id, legacy_ok=False), prov)
    except OSError as e:
        return {"ok": False,
                "error": f"clone written but provenance failed: {e}",
                "file": os.path.relpath(dst, REPO)}

    return {"ok": True, "id": new_id,
            "file": os.path.relpath(dst, REPO),
            "runtime_copy": os.path.relpath(rt, REPO) if rt else None,
            "applied_ops": applied,
            "next": "call fx_register to expose it to find/scene/play"}


# ---------------------------------------------------------------- patch

def _set_scalar_field(tag: Tag, value: Any, path: str) -> str:
    leaf = path.rsplit(".", 1)[-1]
    leaf = leaf.split("[", 1)[0]

    nf = _nf_constant_value(tag)
    if nf is not None:
        num = nf[1]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{path}: expected number, got {value!r}")
        if num.type in _INT_RANGES:
            _check_int_write(num.type, value, path)
        if leaf in _FIELD_BOUNDS:
            lo, hi = _FIELD_BOUNDS[leaf]
            if not (lo <= float(value) <= hi):
                raise ValueError(f"{path}: {value} outside {lo}..{hi}")
        num.value = int(value) if num.type in _INT_RANGES else float(value)
        return f"{path}: constant -> {num.value}"
    if tag.type == TAG_LIST and tag.value \
            and all(v.type == TAG_FLOAT for v in tag.value):
        if not (isinstance(value, list) and len(value) == len(tag.value)):
            raise TypeError(f"{path}: expected list len {len(tag.value)}")
        for v, x in zip(tag.value, value):
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise TypeError(f"{path}: expected numbers, got {x!r}")
            v.value = float(x)
        return f"{path}: vec -> {value}"
    if tag.type == TAG_STRING:
        if not isinstance(value, str):
            raise TypeError(f"{path}: expected string")
        if leaf in _ENUM_DOMAINS and value not in _ENUM_DOMAINS[leaf]:
            raise ValueError(
                f"{path}: '{value}' not in {sorted(_ENUM_DOMAINS[leaf])}")
        tag.value = value
        return f"{path}: '{value}'"
    if tag.type in _INT_RANGES:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{path}: expected number, got {value!r}")
        _check_int_write(tag.type, value, path)
        if leaf in _FIELD_BOUNDS:
            lo, hi = _FIELD_BOUNDS[leaf]
            if not (lo <= float(value) <= hi):
                raise ValueError(f"{path}: {value} outside {lo}..{hi}")
        tag.value = int(value)
        return f"{path}: -> {tag.value}"
    if tag.type in (TAG_FLOAT, TAG_DOUBLE):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{path}: expected number, got {value!r}")
        if leaf in _FIELD_BOUNDS:
            lo, hi = _FIELD_BOUNDS[leaf]
            if not (lo <= float(value) <= hi):
                raise ValueError(f"{path}: {value} outside {lo}..{hi}")
        tag.value = float(value)
        return f"{path}: -> {tag.value}"
    raise TypeError(f"{path}: field of tag type {tag.type} "
                    "is not scalar-patchable")


def _check_int_write(tag_type: int, value: Any, path: str) -> None:
    """Range/type gate for writes into integer tags — a struct.pack
    overflow must surface as a per-op error, not as a crashed save."""
    if isinstance(value, float) and not value.is_integer():
        raise TypeError(f"{path}: {value} is not integral")
    v = int(value)
    lo, hi = _INT_RANGES[tag_type]
    if not (lo <= v <= hi):
        raise ValueError(f"{path}: {v} outside {tag_type} range "
                         f"{lo}..{hi}")


def _set_color_field(tag: Tag, value: str, path: str) -> str:
    if _nf_color_value(tag) is None:
        raise TypeError(
            f"{path}: not a constant color field "
            f"(type={tag.get('type').value if _is_numfunc(tag) else tag.type})")
    # docs and inspect output both use #AARRGGBB; #RRGGBB means opaque.
    m = re.fullmatch(r"#?([0-9a-fA-F]{8}|[0-9a-fA-F]{6})", value)
    if not m:
        raise TypeError(f"{path}: expected #RRGGBB or #AARRGGBB, "
                        f"got {value!r}")
    argb = int(m.group(1), 16)
    if len(m.group(1)) == 6:
        argb |= 0xFF000000
    if argb >= 0x80000000:
        argb -= 0x100000000
    tag.get("data").get("number").value = argb
    return f"{path}: color -> {_hex_argb(argb)}"


def _dig(parent: Tag, path: str) -> Tag:
    """path a.b[0].c within an emitter's config.

    Refuses to descend inside a number-function wrapper (its `type`/`data`
    interior is structure, not a semantic field) and into `_`-prefixed
    keys (`_enable`, `_parentId`, ... are managed by toggle/clone ops)."""
    cur = parent
    for part in path.split("."):
        m = re.fullmatch(r"([A-Za-z_0-9]+)(\[(\d+)\])?", part)
        if not m:
            raise KeyError(f"bad path segment '{part}'")
        key, idx = m.group(1), m.group(3)
        if key.startswith("_"):
            raise KeyError(f"'{key}' is an internal field — not patchable")
        if _numfunc_shaped(cur):
            raise KeyError(f"'{key}': cannot descend inside a "
                           "number-function — patch the field itself")
        cur = cur.get(key) if cur.type == TAG_COMPOUND else None
        if cur is None:
            raise KeyError(f"no field '{key}'")
        if idx is not None:
            i = int(idx)
            if cur.type != TAG_LIST or i >= len(cur.value):
                raise KeyError(f"'{key}[{i}]' not a list slot")
            cur = cur.value[i]
    return cur


def _scrub_object_refs(objs: Tag, oid: str) -> None:
    """After removing the fxObject with transform id `oid`, scrub every
    reference: drop it from _childrenId lists, reset _parentId and any
    uuid string inside configs (TransformRef fields) to "_NULL_"."""
    def reset(t: Tag) -> None:
        if t.value == oid:
            t.value = "_NULL_"

    for o in objs.value:
        data = o.get("data") if o.type == TAG_COMPOUND else None
        if not data:
            continue
        tr = data.get("transform")
        if tr:
            ch = tr.get("_childrenId")
            if ch and ch.type == TAG_LIST:
                ch.value = [c for c in ch.value if c.value != oid]
            par = tr.get("_parentId")
            if par and par.type == TAG_STRING and par.value == oid:
                par.value = "_NULL_"
        cfg = data.get("config")
        if cfg:
            _walk_tag_strings(cfg, reset)


def apply_ops(root: Tag, ops: list[dict[str, Any]]) -> tuple[list, list]:
    """Apply semantic patch ops to a decoded root. Returns (applied, errors)."""
    objs = _objects(root)
    applied, errors = [], []
    for op in ops:
        if not isinstance(op, dict):
            errors.append(f"op {op!r}: not an object")
            continue
        kind = op.get("op")
        target = str(op.get("emitter", "0"))
        try:
            m = _EMITTER_SEL_RE.match(target)
            if kind == "toggle" and m:
                idx, _ = _resolve_emitter(objs, m.group(1))
                if op.get("value") in (False, "off", 0):
                    if len(objs.value) <= 1:
                        raise ValueError("cannot disable the only emitter")
                    oid = _emitter_oid(objs.value[idx], idx)
                    del objs.value[idx]
                    _scrub_object_refs(objs, oid)
                    applied.append(f"emitter:{m.group(1)} removed — "
                                   "note: emitter indices after this "
                                   "point shift by one")
                else:
                    raise ValueError("re-enabling a removed emitter is not "
                                     "supported — re-clone instead")
                continue

            idx, obj = _resolve_emitter(objs, target)
            data = obj.get("data") if obj.type == TAG_COMPOUND else None
            cfg = data.get("config") if data else None
            if cfg is None or cfg.type != TAG_COMPOUND:
                raise KeyError("emitter has no config")

            field = op.get("field")
            if kind in ("scalar", "color", "toggle"):
                if not isinstance(field, str) or not field:
                    raise KeyError(f"op {op}: 'field' must be a path string")
            if "value" not in op:
                raise KeyError(f"op {op}: missing 'value'")

            if kind == "scalar":
                f = _dig(cfg, field)
                applied.append(_set_scalar_field(f, op["value"],
                                                 f"{target}.{field}"))
            elif kind == "color":
                f = _dig(cfg, field)
                applied.append(_set_color_field(f, op["value"],
                                                f"{target}.{field}"))
            elif kind == "toggle":
                comp = _dig(cfg, field)
                if comp.type != TAG_COMPOUND or comp.get("_enable") is None:
                    raise TypeError(
                        f"{target}.{field}: not a toggleable layer "
                        "(no _enable flag)")
                val = op["value"]
                if val in (True, "on", 1):
                    on = True
                elif val in (False, "off", 0):
                    on = False
                else:
                    raise ValueError(f"{target}.{field}: toggle value "
                                     f"{val!r} — use true/false/on/off")
                comp.get("_enable").value = 1 if on else 0
                applied.append(
                    f"{target}.{field}: _enable -> {1 if on else 0}")
            else:
                raise ValueError(f"unknown op '{kind}' "
                                 "(use scalar|color|toggle)")
        except (KeyError, IndexError, TypeError, ValueError,
                AttributeError) as e:
            errors.append(f"op {op}: {e}")
    return applied, errors


def _emitter_oid(obj: Tag, idx: int) -> str:
    data = obj.get("data") if obj.type == TAG_COMPOUND else None
    tr = data.get("transform") if data else None
    if tr and tr.get("id") and tr.get("id").type == TAG_STRING:
        return tr.get("id").value
    raise ValueError(f"fxObjects[{idx}] has no transform.id — "
                     "cannot remove it safely")


def patch_fx(resource_id: str, ops: list[dict[str, Any]],
             allow_stock: bool = False) -> dict[str, Any]:
    """Patch a cloned .fx in place (both src + runtime copies).

    Refuses ids without a provenance file — stock fixtures are read-only
    by contract (clone first). Pass allow_stock=True only for deliberate
    fixture regeneration."""
    if ops is None or not isinstance(ops, list):
        return {"ok": False, "errors": ["ops must be a list of op objects"]}
    if not allow_stock and not os.path.exists(_prov_path(resource_id)):
        return {"ok": False,
                "errors": [f"'{resource_id}' is not a clone (no provenance "
                           "file) — clone it first with fx_clone; "
                           "stock fixtures are never patched"]}
    path = fx_file_path(resource_id)
    if not os.path.exists(path):
        alt = resolve_fx_file(resource_id)
        if alt is None:
            return {"ok": False, "errors": [f"no .fx file for '{resource_id}'"]}
        path = alt
    try:
        name, root = load_fx(path)
    except Exception as e:
        return {"ok": False, "errors": [f"unreadable .fx: {e}"]}
    applied, errors = apply_ops(root, ops)
    if errors:
        # nothing persisted — 'applied' is what would have applied
        return {"ok": False, "applied": [], "errors": errors,
                "note": "no ops were persisted"}
    try:
        save_fx(path, name, root)
    except (OSError, ValueError, struct.error) as e:
        return {"ok": False, "applied": [], "errors": [f"encode failed: {e}"]}
    rt = fx_file_path(resource_id, FX_RUNTIME_DIR)
    if os.path.exists(rt):
        try:
            shutil.copyfile(path, rt)
        except OSError:
            pass
    prov_path = _prov_path(resource_id)
    if os.path.exists(prov_path):
        try:
            prov = json.load(open(prov_path))
            prov.setdefault("ops", []).extend(ops)
            prov.setdefault("ops_history", []).append(
                {"at": time.time(), "ops": ops})
            _atomic_write_json(prov_path, prov)
        except (OSError, ValueError):
            pass
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
        return {"ok": False, "errors": [str(e)], "warnings": warnings}
    if not objs.value:
        warnings.append("empty fxObjects — effect will render nothing")
    seen_ids: set[str] = set()
    for i, o in enumerate(objs.value):
        lab = f"fxObjects[{i}]"
        if o.type != TAG_COMPOUND:
            errors.append(f"{lab}: not a compound (tag {o.type})")
            continue
        ot = o.get("type")
        if ot is None or ot.type != TAG_STRING \
                or ot.value not in FX_OBJECT_TYPES:
            errors.append(f"{lab}: unknown object type "
                          f"'{ot.value if ot else None}'")
        data = o.get("data")
        if data is None or data.type != TAG_COMPOUND:
            errors.append(f"{lab}: missing data compound")
            continue
        tr = data.get("transform")
        if tr is None or tr.type != TAG_COMPOUND \
                or tr.get("id") is None:
            errors.append(f"{lab}: no transform.id")
        else:
            oid = tr.get("id").value
            if oid in seen_ids:
                warnings.append(f"{lab}: duplicate object id {oid}")
            seen_ids.add(oid)
        cfg = data.get("config")
        if cfg is None or cfg.type != TAG_COMPOUND:
            errors.append(f"{lab}: no config")
        else:
            _validate_numfuncs(cfg, lab, warnings, depth=0)
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "emitters": len(objs.value)}


def _validate_numfuncs(tag: Tag, lab: str, warnings: list[str],
                       depth: int) -> None:
    """Warn on number-function-shaped compounds whose type name is not in
    the Photon registry — reachable, unlike the previous dead check."""
    if tag.type == TAG_COMPOUND:
        for k, t in tag.value:
            if _numfunc_shaped(t) and t.get("type").value \
                    not in NUMBER_FUNCTION_TYPES:
                warnings.append(f"{lab}.{k}: odd numfunc type "
                                f"'{t.get('type').value}'")
            elif depth < 4:
                _validate_numfuncs(t, f"{lab}.{k}", warnings, depth + 1)
    elif tag.type == TAG_LIST and depth < 4:
        for i, t in enumerate(tag.value):
            _validate_numfuncs(t, f"{lab}[{i}]", warnings, depth + 1)


# ---------------------------------------------------------------- register

def register_fx(resource_id: str, source_id: str | None = None) -> dict[str, Any]:
    """Make a cloned .fx a first-class catalog resource."""
    try:
        with open(CATALOG) as f:
            cat = json.load(f)
    except (OSError, ValueError) as e:
        return {"ok": False, "error": f"catalog unreadable: {e}"}
    resources = cat.get("resources")
    if not isinstance(resources, list):
        return {"ok": False, "error": "catalog has no resources list"}
    if any(r.get("id") == resource_id for r in resources):
        return {"ok": False, "error": f"'{resource_id}' already in catalog"}

    v = validate_fx(resource_id)
    if not v["ok"]:
        return {"ok": False, "error": "validation failed",
                "validation": v}

    prov_path = _prov_path(resource_id)
    try:
        prov = (json.load(open(prov_path)) if os.path.exists(prov_path)
                else {"source": source_id or "unknown", "ops": []})
    except (OSError, ValueError):
        prov = {"source": source_id or "unknown", "ops": []}
    src_id = prov.get("source") or source_id or "unknown"
    src = next((r for r in resources if r.get("id") == src_id), None)

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
        "diagnostics": [],
    }
    if src:
        # factual / roles / capabilities describe resource kind and are
        # patch-insensitive — safe to inherit. measured/visual describe
        # the SOURCE's captured look: a patch can change exactly those
        # (color, counts), so the clone must NOT claim them — Jev would
        # rank on untruth. The full source passport stays reachable via
        # provenance + diagnostics.
        for key in ("possible_roles", "capabilities"):
            if src.get(key) is not None:
                passport[key] = src[key]
        passport["visual_status"] = "inherited"
        passport["visual_status_reason"] = (
            f"not captured; source {src_id} has observed visuals — "
            "see its passport for the un-patched look")
        passport["diagnostics"].append(
            f"clone of {src_id}; measured/visual deliberately NOT "
            f"inherited (patches may change them); patches applied: "
            f"{len(prov.get('ops', []))}; re-capture to refresh")
    else:
        passport["diagnostics"].append(
            f"clone of {src_id} (source not in catalog); no inherited "
            "measured/visual data; patches applied: "
            f"{len(prov.get('ops', []))}")

    resources.append(passport)
    cat.setdefault("diagnostics", []).append(
        f"{time.strftime('%Y-%m-%d')}: registered {resource_id} "
        f"(clone of {src_id})")
    _recount_catalog_stats(cat)
    try:
        _atomic_write(CATALOG, json.dumps(cat, ensure_ascii=False,
                                          indent=1).encode("utf-8"))
    except OSError as e:
        return {"ok": False, "error": f"catalog write failed: {e}"}

    return {"ok": True, "id": resource_id,
            "source": src_id,
            "catalog": os.path.relpath(CATALOG, REPO),
            "ready_to_use": True,
            "next": "usable via vfx_find/vfx_inspect/vfx_scene_* "
                    "and spawn kind 'fx'"}


def _recount_catalog_stats(cat: dict[str, Any]) -> None:
    """Keep catalog stats honest after appending a passport — the file is
    consumed by tools that trust stats.total/by_kind/by_source."""
    resources = cat.get("resources") or []
    stats = cat.setdefault("stats", {})
    stats["total"] = len(resources)
    by_kind: dict[str, int] = {}
    by_source: dict[str, int] = {}
    answerable = 0
    for r in resources:
        k = r.get("kind") or "?"
        by_kind[k] = by_kind.get(k, 0) + 1
        s = r.get("source") or "?"
        by_source[s] = by_source.get(s, 0) + 1
        if r.get("ready_to_use"):
            answerable += 1
    stats["by_kind"] = by_kind
    stats["by_source"] = by_source
    if "answerable" in stats:
        stats["answerable"] = answerable
    if "parameterized" in stats:
        stats["parameterized"] = sum(1 for r in resources if r.get("parameterized"))
    if "primitives" in stats:
        stats["primitives"] = sum(1 for r in resources if r.get("primitive"))
