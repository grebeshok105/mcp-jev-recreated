"""jevlab VFX MCP server (stdio).

Tools:
  vfx_find(query, top_k)          — Jev ranking over the catalog -> top-k ids
  vfx_inspect(id)                 — full passport (factual+measured+visual)
  vfx_preview(id)                 — catalog capture artifacts: contact sheet,
                                    per-angle frames, visual summary
  vfx_scene_validate(scene_json)  — validate a scene spec against the catalog
  vfx_scene_plan(scene_json)      — validate + compile to the probe plan
  vfx_scene_play(scene_json)      — compile + exact runtime playback in the
                                    real client -> frames + measurements

Env: TYPESAFE_API_KEY for vfx_find; repo layout must be intact (data/catalog.json,
data/capture/...). Run: `python -m jevlab.mcp_server`.
"""
from __future__ import annotations

import json
import os

from mcp.server.mcpserver import MCPServer

from .find_effects import find
from .scene.compile import compile_scene, load_level_events
from .scene.play import (LEVEL_EVENTS, PlaybackResult, load_catalog_index,
                         play_scene)
from .scene.spec import validate_scene

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
CATALOG_PATH = os.path.join(DATA, "catalog.json")
SHEET_MANIFEST = os.path.join(DATA, "capture", "sheet_manifest.json")
FRAMES_INDEX = os.path.join(DATA, "capture", "measurements", "frames_index.json")

mcp = MCPServer("jevlab-vfx")

_catalog_index: dict[str, dict] | None = None


def _index() -> dict[str, dict]:
    global _catalog_index
    if _catalog_index is None:
        _catalog_index = load_catalog_index()
    return _catalog_index


def _scene_arg(scene) -> dict:
    if isinstance(scene, str):
        return json.loads(scene)
    return dict(scene)


@mcp.tool()
def vfx_find(query: str, top_k: int = 10) -> dict:
    """Rank the catalog's spawnable VFX candidates for a natural-language
    effect description via live Jev (TypeSafe). Returns the top-k ids with
    choice probabilities, plus candidate count and cache status."""
    result, meta = find(query, CATALOG_PATH, top_k=top_k)
    top = [
        {"rank": c["rank"], "id": c["id"], "kind": c["kind"],
         "noul_relevance": c["noul_relevance"],
         "choice_probability": c["choice_probability"],
         "summary": c["summary"]}
        for c in result.get("candidates", [])
    ]
    return {
        "query": query,
        "candidates_evaluated": meta["candidates"],
        "query_cache": meta["query_cache"],
        "top": top,
        "stats": result.get("stats", {}),
        "diagnostics": result.get("diagnostics", []),
    }


@mcp.tool()
def vfx_inspect(resource_id: str) -> dict:
    """Full catalog passport for a resource id: kind, factual data, measured
    spawn stats, visual semantics (when observed), parameter schema,
    provenance. This is the FAT view — for ranking use vfx_find."""
    r = _index().get(resource_id)
    if r is None:
        return {"error": f"unknown resource '{resource_id}'",
                "hint": "call vfx_find to discover ids"}
    return r


@mcp.tool()
def vfx_preview(resource_id: str) -> dict:
    """What the resource actually looked like in the probe capture: contact
    sheet URL (all angles x ticks), per-angle frame file paths, and the
    merged visual semantics + reliability status."""
    r = _index().get(resource_id)
    if r is None:
        return {"error": f"unknown resource '{resource_id}'"}
    key = resource_id.replace(":", "_").replace("/", "_")
    out = {"id": resource_id, "kind": r.get("kind"),
           "visual_status": r.get("visual_status"),
           "visual_status_reason": r.get("visual_status_reason"),
           "visual": r.get("visual")}
    manifest = {}
    if os.path.exists(SHEET_MANIFEST):
        manifest = json.load(open(SHEET_MANIFEST))
    out["contact_sheet_url"] = manifest.get(key)
    if os.path.exists(FRAMES_INDEX):
        idx = json.load(open(FRAMES_INDEX))
        out["frames"] = {k: v for k, v in idx.items()
                         if k.startswith(key + "__")}
    else:
        out["frames"] = {}
    if r.get("kind") == "world_event":
        name = r.get("factual", {}).get("event_name", "")
        ekey = f"world_event_{name}"
        if ekey in manifest:
            out["contact_sheet_url"] = manifest[ekey]
            if os.path.exists(FRAMES_INDEX):
                idx = json.load(open(FRAMES_INDEX))
                out["frames"] = {k: v for k, v in idx.items()
                                 if k.startswith(ekey + "__")}
    if not out.get("contact_sheet_url") and not out.get("frames"):
        out["note"] = ("no capture artifacts — composite bundles and "
                       "non-spawnable kinds have nothing to preview")
    return out


@mcp.tool()
def vfx_scene_validate(scene: dict) -> dict:
    """Validate a scene spec against the catalog. Scene shape (v2):

      {"name": str,
       "scene": {"pos":[x,lift,z], "time":int, "weather":"clear|rain|thunder"},
       "camera": {"angles":[front|back|side|side_right|top|threequarter|low|far]},
       "duration": ticks, "frames": [ticks to screenshot],
       "steps": [{
         "tick": int,                      # 0 fires at scene start
         "id": resource_id,
         "name": str,                      # gives this step's spawn pos a ref name
         "anchor": "scene|player[.feet|.chest|.head|.look]|camera|ref:<name>"
                 or {"anchor":..., "offset":[x,y,z], "distance":n,
                     "direction":"world|player.look|[yaw,pitch]|{\"face\":<expr>}"},
         "offset": [x,y,z], "direction": ..., "distance": n,
         "pos": [x,y,z],                   # local-frame offset, rotates with direction
         "to": <anchor expr>,              # aim the effect at a target
         "follow": "player",               # re-resolve the anchor every tick
         "track": {"pos":[[t,x,y,z]...],   # keyframes relative to spawn tick
                   "rotation":[[t,yaw,pitch]...], "scale":[[t,s]...]},
         "repeat": {"every":T,"count":N} | {"every":T,"until":M},
         "options": {...}, "stop_after": bool}],
       "groups": [{"tick":T, "repeat":{...}, "steps":[member steps...]}],
       "commands": [{"tick":int, "command":"server console command"}]}

    Returns {ok, errors, warnings, normalized}."""
    v = validate_scene(_scene_arg(scene), _index())
    return {"ok": v.ok, "errors": v.errors, "warnings": v.warnings,
            "normalized": v.normalized}


@mcp.tool()
def vfx_scene_plan(scene: dict) -> dict:
    """Validate + compile a scene spec into the probe playback plan that
    vfx_scene_play (and the Java scenario) consumes. Same spec shape as
    vfx_scene_validate."""
    events = load_level_events(LEVEL_EVENTS)
    plan, v = compile_scene(_scene_arg(scene), _index(), events)
    return {"ok": v.ok and plan is not None, "errors": v.errors,
            "warnings": v.warnings, "plan": plan}


@mcp.tool()
def vfx_scene_play(scene: dict, timeout_s: int = 900) -> dict:
    """Compile the scene spec and run exact runtime playback in the real
    1.21.1 client (probe vfxlab.4_scene via ./gradlew runUitest). Replays the
    tick timeline once per camera angle, screenshots the requested frame
    ticks, and returns per-angle particle measurements + frame paths.

    This launches a real game client — expect tens of seconds to a few
    minutes depending on duration and angle count."""
    res: PlaybackResult = play_scene(
        _scene_arg(scene), timeout_s=timeout_s, catalog_index=_index())
    out = {"ok": res.ok, "errors": res.errors, "warnings": res.warnings,
           "plan_path": res.plan_path, "frames": res.frames,
           "results": res.results}
    if not res.ok and res.gradle_tail:
        out["gradle_tail"] = res.gradle_tail[-15:]
    return out


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
