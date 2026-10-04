#!/usr/bin/env python3
"""Generate data/capture/capture_plan.json for all spawnable answerable
resources in data/catalog.json.

Kinds covered: particle, parameterized_particle, world_event(has_visual),
fx, quasar_emitter. `composite` resources are Codex vfx parameter bundles
(tuning JSON consumed by ability code, no standalone spawn path) — they are
emitted to the exceptions list instead of the plan.

Usage: python tools/gen_capture_plan.py [--out data/capture/capture_plan.json]
Prints a summary plus the exception list on stdout.
"""
from __future__ import annotations

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CATALOG = os.path.join(ROOT, "data", "catalog.json")
LEVEL_EVENTS = os.path.join(ROOT, "data", "capture", "dump", "level_events.json")
DEFAULT_OUT = os.path.join(ROOT, "data", "capture", "capture_plan.json")

ANSWERABLE = {"particle", "parameterized_particle", "world_event", "fx",
              "quasar_emitter", "composite"}

# per-particle spawn options: count/delta tuned so the captured burst reads
# well at eye level. Anything not listed gets the DEFAULT_SPEC.
DEFAULT_SPEC = {"count": 8, "delta": 0.4}

PARTICLE_SPECS: dict[str, dict] = {
    # one-shot bursts / emitters — count 1 keeps the shape readable
    "minecraft:sonic_boom": {"count": 1},
    "minecraft:explosion_emitter": {"count": 1},
    "minecraft:explosion": {"count": 2, "delta": 0.3},
    "minecraft:flash": {"count": 2},
    "minecraft:gust": {"count": 1},
    "minecraft:gust_emitter_large": {"count": 1},
    "minecraft:gust_emitter_small": {"count": 1},
    "minecraft:small_gust": {"count": 2},
    "minecraft:sweep_attack": {"count": 3},
    "minecraft:dust_plume": {"count": 3},
    "minecraft:dragon_fireball": {"count": 1},
    "minecraft:white_smoke": {"count": 10},
    "minecraft:poof": {"count": 8, "delta": 0.5},
    # fire / smoke columns
    "minecraft:flame": {"count": 8, "delta": 0.5},
    "minecraft:small_flame": {"count": 10, "delta": 0.5},
    "minecraft:soul_fire_flame": {"count": 10, "delta": 0.5},
    "minecraft:lava": {"count": 4},
    "minecraft:smoke": {"count": 8, "delta": 0.4},
    "minecraft:large_smoke": {"count": 8, "delta": 0.4},
    "minecraft:campfire_cosy_smoke": {"count": 6},
    "minecraft:campfire_signal_smoke": {"count": 6},
    "minecraft:firework": {"count": 12, "delta": 0.6},
    # magic / bursts
    "minecraft:effect": {"count": 10, "delta": 0.5},
    "minecraft:instant_effect": {"count": 10, "delta": 0.5},
    "minecraft:witch": {"count": 10, "delta": 0.5},
    "minecraft:crit": {"count": 10, "delta": 0.5},
    "minecraft:enchanted_hit": {"count": 10, "delta": 0.5},
    "minecraft:damage_indicator": {"count": 8, "delta": 0.5},
    "minecraft:totem": {"count": 15, "delta": 0.6},
    "minecraft:enchant": {"count": 10},
    "minecraft:nautilus": {"count": 10},
    "minecraft:happy_villager": {"count": 8, "delta": 0.5},
    "minecraft:angry_villager": {"count": 5, "delta": 0.5},
    "minecraft:composter": {"count": 5},
    "minecraft:egg_crack": {"count": 5},
    "minecraft:heart": {"count": 3},
    "minecraft:note": {"count": 8},
    "minecraft:portal": {"count": 20, "delta": 0.3},
    "minecraft:reverse_portal": {"count": 20, "delta": 0.3},
    "minecraft:end_rod": {"count": 8, "delta": 0.3},
    "minecraft:dragon_breath": {"count": 25, "delta": 0.4},
    "minecraft:squid_ink": {"count": 8},
    "minecraft:bubble_pop": {"count": 15, "delta": 0.5},
    "minecraft:bubble": {"count": 15, "delta": 0.3},
    "minecraft:bubble_column_up": {"count": 15, "delta": 0.3},
    "minecraft:current_down": {"count": 15, "delta": 0.3},
    "minecraft:dolphin": {"count": 10},
    "minecraft:splash": {"count": 15, "delta": 0.5},
    "minecraft:fishing": {"count": 10, "delta": 0.5},
    "minecraft:underwater": {"count": 15, "delta": 0.6},
    "minecraft:suspended": {"count": 15, "delta": 0.6},
    "minecraft:suspended_depth": {"count": 15, "delta": 0.6},
    "minecraft:rain": {"count": 30, "delta": 1.5},
    "minecraft:ash": {"count": 15, "delta": 0.8},
    "minecraft:crimson_spore": {"count": 15, "delta": 0.8},
    "minecraft:warped_spore": {"count": 15, "delta": 0.8},
    "minecraft:spore_blossom_air": {"count": 15, "delta": 1.0},
    "minecraft:falling_spore_blossom": {"count": 10, "delta": 0.5},
    "minecraft:mycelium": {"count": 15, "delta": 1.0},
    "minecraft:soul": {"count": 8, "delta": 0.4},
    "minecraft:sculk_soul": {"count": 5, "delta": 0.4},
    "minecraft:electric_spark": {"count": 15, "delta": 0.8},
    "minecraft:scrape": {"count": 5},
    "minecraft:wax_on": {"count": 5},
    "minecraft:wax_off": {"count": 5},
    # gravity-driven
    "minecraft:cherry_leaves": {"count": 10, "delta": 1.0},
    "minecraft:pale_oak_leaves": {"count": 10, "delta": 1.0},
    "minecraft:dripping_water": {"count": 5, "delta": 0.3},
    "minecraft:dripping_lava": {"count": 5, "delta": 0.3},
    "minecraft:dripping_honey": {"count": 5, "delta": 0.3},
    "minecraft:dripping_obsidian_tear": {"count": 5, "delta": 0.3},
    "minecraft:dripping_dripstone_water": {"count": 5, "delta": 0.3},
    "minecraft:dripping_dripstone_lava": {"count": 5, "delta": 0.3},
    "minecraft:falling_water": {"count": 8, "delta": 0.3},
    "minecraft:falling_lava": {"count": 8, "delta": 0.3},
    "minecraft:falling_honey": {"count": 8, "delta": 0.3},
    "minecraft:falling_nectar": {"count": 8, "delta": 0.3},
    "minecraft:falling_obsidian_tear": {"count": 8, "delta": 0.3},
    "minecraft:falling_dripstone_water": {"count": 8, "delta": 0.3},
    "minecraft:falling_dripstone_lava": {"count": 8, "delta": 0.3},
    "minecraft:landing_lava": {"count": 8},
    "minecraft:landing_honey": {"count": 8},
    "minecraft:landing_obsidian_tear": {"count": 8},
    # fast movers — low count, caught early frames
    "minecraft:spit": {"count": 3},
    "minecraft:sneeze": {"count": 5},
    "minecraft:item_slime": {"count": 5},
    "minecraft:item_snowball": {"count": 5},
    "minecraft:item_cobweb": {"count": 5},
    # trial/ominous sets
    "minecraft:infested": {"count": 10, "delta": 0.5},
    "minecraft:raid_omen": {"count": 5},
    "minecraft:trial_omen": {"count": 5},
    "minecraft:trial_spawner_detection": {"count": 10, "delta": 0.5},
    "minecraft:trial_spawner_detection_ominous": {"count": 10, "delta": 0.5},
    "minecraft:vault_connection": {"count": 1},
    "minecraft:ominous_spawning": {"count": 8},
    "minecraft:small_flame_like": {"count": 8},
    "minecraft:firefly": {"count": 8, "delta": 0.6},
    "minecraft:dust_pillar": {"count": 1, "block": "minecraft:stone"},
}

# parameterized types needing an explicit option payload
PARAM_SPECS: dict[str, dict] = {
    "minecraft:dust": {"count": 30, "color": [0.1, 0.8, 1.0], "scale": 2,
                       "delta": 0.4},
    "minecraft:dust_color_transition": {"count": 20, "from_color": [0.1, 0.5, 1.0],
                                        "to_color": [0.9, 0.2, 0.8], "scale": 2,
                                        "delta": 0.4},
    "minecraft:block": {"count": 15, "block": "minecraft:stone", "delta": 0.5},
    "minecraft:block_marker": {"count": 5, "block": "minecraft:stone"},
    "minecraft:falling_dust": {"count": 15, "block": "minecraft:stone",
                               "delta": 1.0},
    "minecraft:dust_pillar": {"count": 1, "block": "minecraft:stone"},
    "minecraft:item": {"count": 10, "item": "minecraft:apple", "delta": 0.5},
    "minecraft:entity_effect": {"count": 10, "color": [1.0, 0.5, 0.1],
                                "delta": 0.5},
    "minecraft:sculk_charge": {"count": 1, "roll": 0},
    "minecraft:shriek": {"count": 1, "delay": 0},
    "minecraft:vibration": {"count": 1, "destination": [8.5, 3.0, 8.5],
                            "arrival_in_ticks": 20},
}

# world events that take block-state data -> resolve via a real block
EVENT_DATA_BLOCK = {
    "PARTICLES_DESTROY_BLOCK": "minecraft:stone",
    "PARTICLES_AND_SOUND_BRUSH_BLOCK_COMPLETE": "minecraft:stone",
    "PARTICLES_DRAGON_BLOCK_BREAK": "minecraft:stone",
}
# world events taking an int data value
EVENT_DATA_INT = {
    "PARTICLES_SHOOT_SMOKE": 3,          # direction ordinal (south-ish)
    "PARTICLES_SHOOT_WHITE_SMOKE": 3,
    "PARTICLES_SPELL_POTION_SPLASH": 0xFF6633,   # splash potion ARGB
    "PARTICLES_INSTANT_POTION_SPLASH": 0x33CCFF,
    "PARTICLES_MOBBLOCK_SPAWN": 128,     # entity size * 128
    "PARTICLES_AND_SOUND_PLANT_GROWTH": 15,      # bonemeal particle count
    "PARTICLES_BEE_GROWTH": 5,
    "PARTICLES_ELECTRIC_SPARK": 2,       # spark orientation 0..7
    "PARTICLES_TRIAL_SPAWNER_DETECT_PLAYER_OMINOUS": 1,
    "PARTICLES_TRIAL_SPAWNER_DETECT_PLAYER": 0,
}


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
        kind = r["kind"]
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "composite":
            exceptions.append({
                "id": r["id"],
                "kind": kind,
                "reason": ("Codex vfx parameter bundle (tuning JSON consumed "
                           "by ability code; no standalone emitter/asset to "
                           "spawn — verified: file contains only scalar "
                           "tuning fields)"),
            })
            continue
        if kind == "particle":
            spec = dict(DEFAULT_SPEC)
            spec.update(PARTICLE_SPECS.get(r["id"], {}))
            shots.append({"id": r["id"], "kind": "particle", "options": spec})
        elif kind == "parameterized_particle":
            spec = dict(PARAM_SPECS.get(r["id"], {}))
            shots.append({"id": r["id"], "kind": "particle", "options": spec})
        elif kind == "world_event":
            name = r["factual"]["event_name"]
            if name not in events:
                exceptions.append({"id": r["id"], "kind": kind,
                                   "reason": "event name missing from dump"})
                continue
            shot = {"id": f"world_event_{name}", "kind": "level_event",
                    "event": events[name]}
            if name in EVENT_DATA_BLOCK:
                shot["data_block"] = EVENT_DATA_BLOCK[name]
            elif name in EVENT_DATA_INT:
                shot["data_int"] = EVENT_DATA_INT[name]
            shots.append(shot)
        elif kind == "fx":
            shots.append({"id": r["id"], "kind": "fx", "options": {}})
        elif kind == "quasar_emitter":
            shots.append({"id": r["id"], "kind": "quasar_emitter",
                          "options": {}})
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
