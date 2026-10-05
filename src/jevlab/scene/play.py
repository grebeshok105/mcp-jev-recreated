"""Run a compiled scene plan inside the real client via the probe's
`vfxlab.4_scene` uitest scenario, and collect the artifacts.

`play_scene` accepts either a raw scene spec (validated + compiled against
the catalog) or a pre-compiled plan; writes `data/capture/scene/scene_plan.json`;
launches `./gradlew runUitest` restricted to the scene scenario; then reads
back `scene_results.json` + the runner screenshots.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

from .compile import compile_scene, load_level_events, write_plan
from .spec import validate_scene

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DATA = os.path.join(ROOT, "data")
CATALOG = os.path.join(DATA, "catalog.json")
LEVEL_EVENTS = os.path.join(DATA, "capture", "dump", "level_events.json")
SCENE_DIR = os.path.join(DATA, "capture", "scene")
SCENE_PLAN = os.path.join(SCENE_DIR, "scene_plan.json")
SCENE_RESULTS = os.path.join(SCENE_DIR, "scene_results.json")
SCENE_FRAMES_INDEX = os.path.join(
    DATA, "capture", "measurements", "scene_frames_index.json")
UITEST_SCREENSHOTS = os.path.join(
    DATA, "uitest-report", "screenshots", "vfxlab.4_scene")
PROBE_DIR = os.path.join(ROOT, "probe")


@dataclass
class PlaybackResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    plan_path: str | None = None
    frames: dict[str, str] = field(default_factory=dict)   # label -> path
    results: dict | None = None
    gradle_tail: list[str] = field(default_factory=list)


def load_catalog_index(catalog_path: str = CATALOG) -> dict[str, dict]:
    cat = json.load(open(catalog_path))
    return {r["id"]: r for r in cat["resources"]}


def _clear_prior_outputs() -> None:
    for p in (SCENE_RESULTS, SCENE_FRAMES_INDEX):
        if os.path.exists(p):
            os.remove(p)
    if os.path.isdir(UITEST_SCREENSHOTS):
        for f in os.listdir(UITEST_SCREENSHOTS):
            os.remove(os.path.join(UITEST_SCREENSHOTS, f))


def play_scene(spec_or_plan: dict, *, timeout_s: int = 900,
               catalog_index: dict[str, dict] | None = None,
               dry_run: bool = False) -> PlaybackResult:
    """Compile (if needed), write the plan, run the client, collect results.

    `dry_run=True` stops after writing the plan (no gradle launch).
    """
    res = PlaybackResult(ok=False)
    catalog_index = catalog_index or load_catalog_index()

    if "steps" in spec_or_plan and spec_or_plan["steps"] and \
            isinstance(spec_or_plan["steps"][0].get("shot"), dict):
        plan = spec_or_plan  # already compiled
        v = validate_scene(
            {"name": plan.get("name"), "duration": plan.get("duration", 60),
             "steps": [{"id": s["shot"].get("id"), "tick": s.get("at_tick", 0)}
                       for s in plan["steps"]]},
            catalog_index)
        res.warnings.extend(v.warnings)
    else:
        events = load_level_events(LEVEL_EVENTS)
        plan, v = compile_scene(spec_or_plan, catalog_index, events)
        res.errors.extend(v.errors)
        res.warnings.extend(v.warnings)
        if plan is None:
            return res

    res.plan_path = write_plan(plan, SCENE_PLAN)
    if dry_run:
        res.ok = True
        return res

    _clear_prior_outputs()
    env = dict(os.environ)
    # the shell env may carry an older JDK (e.g. Java 17); loom needs 21+
    env["JAVA_HOME"] = os.environ.get(
        "VFXLAB_JAVA_HOME", os.path.expanduser("~/.jdks/temurin-21"))
    cmd = ["xvfb-run", "-a", "./gradlew", "runUitest", "--no-daemon",
           "-Pvfxlab.uitestSelection=vfxlab.4_scene"]
    try:
        proc = subprocess.run(cmd, cwd=PROBE_DIR, env=env,
                              capture_output=True, text=True,
                              timeout=timeout_s)
        out = (proc.stdout or "") + (proc.stderr or "")
        res.gradle_tail = out.strip().splitlines()[-40:]
        if proc.returncode != 0:
            res.errors.append(f"runUitest exited {proc.returncode}")
            return res
    except subprocess.TimeoutExpired:
        res.errors.append(f"runUitest timed out after {timeout_s}s")
        return res

    if os.path.exists(SCENE_RESULTS):
        res.results = json.load(open(SCENE_RESULTS))
    else:
        res.errors.append("scene_results.json missing — scenario did not "
                          "write results")
        return res
    if os.path.exists(SCENE_FRAMES_INDEX):
        res.frames = json.load(open(SCENE_FRAMES_INDEX))
    res.ok = True
    return res
