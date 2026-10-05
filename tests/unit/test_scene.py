"""Scene lane tests: spec validation + compilation to the probe plan."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))

from jevlab.scene.compile import compile_scene
from jevlab.scene.spec import validate_scene
from jevlab.scene.spawn_specs import shot_spec_for

EVENTS = {"PARTICLES_DESTROY_BLOCK": 2001}

CAT = {
    "minecraft:sonic_boom": {
        "id": "minecraft:sonic_boom", "kind": "particle",
        "ready_to_use": True, "factual": {},
        "visual_status": "observed",
    },
    "minecraft:dust": {
        "id": "minecraft:dust", "kind": "parameterized_particle",
        "parameterized": True,
        "parameter_schema": {
            "color": {"type": "rgb", "default": [1.0, 0.0, 0.0]},
            "scale": {"type": "float", "min": 0.01, "max": 4.0,
                      "default": 1.0},
        },
        "ready_to_use": True, "factual": {},
        "visual_status": "observed",
    },
    "minecraft:dust_color_transition": {
        "id": "minecraft:dust_color_transition",
        "kind": "parameterized_particle", "parameterized": True,
        "parameter_schema": {
            "from_color": {"type": "rgb"}, "to_color": {"type": "rgb"},
            "scale": {"type": "float", "min": 0.01, "max": 4.0},
        },
        "ready_to_use": True, "factual": {},
        "visual_status": "observed",
    },
    "minecraft:bubble": {
        "id": "minecraft:bubble", "kind": "particle",
        "ready_to_use": True, "factual": {},
        "visual_status": "environment_mismatch",
        "visual_status_reason": "requires_water",
    },
    "superheroes:roar_wave": {
        "id": "superheroes:roar_wave", "kind": "quasar_emitter",
        "ready_to_use": True, "factual": {},
        "visual_status": "capture_failed",
        "visual_status_reason": "offscreen",
    },
    "superheroes:vfx/roar": {
        "id": "superheroes:vfx/roar", "kind": "composite",
        "ready_to_use": True, "factual": {},
    },
    "world_event:destroy": {
        "id": "world_event:destroy", "kind": "world_event",
        "ready_to_use": True,
        "factual": {"event_name": "PARTICLES_DESTROY_BLOCK",
                    "has_visual": True},
        "visual_status": "observed",
    },
    "superheroes:fx_ring": {
        "id": "superheroes:fx_ring", "kind": "fx",
        "ready_to_use": True, "factual": {},
        "visual_status": "observed",
    },
}

BASE_SCENE = {"name": "t", "duration": 40,
              "steps": [{"tick": 0, "id": "minecraft:sonic_boom"}]}


def _scene(**kw):
    s = dict(BASE_SCENE)
    s.update(kw)
    return s


def test_validate_ok_normalizes():
    v = validate_scene(BASE_SCENE, CAT)
    assert v.ok, v.errors
    n = v.normalized
    assert n["duration"] == 40
    assert n["frames"] == [3, 8, 20]
    assert n["camera"]["angles"] == ["front"]
    assert n["steps"][0]["pos"] == [0.0, 0.0, 0.0]
    assert n["steps"][0]["stop_after"] is True


def test_validate_unknown_id():
    v = validate_scene(_scene(
        steps=[{"tick": 0, "id": "minecraft:nonexistent_fx"}]), CAT)
    assert not v.ok
    assert any("unknown resource" in e for e in v.errors)


def test_validate_composite_rejected():
    v = validate_scene(_scene(
        steps=[{"tick": 0, "id": "superheroes:vfx/roar"}]), CAT)
    assert not v.ok
    assert any("no standalone spawn path" in e for e in v.errors)


def test_validate_water_warns_not_errors():
    v = validate_scene(_scene(
        steps=[{"tick": 0, "id": "minecraft:bubble"}]), CAT)
    assert v.ok
    assert any("requires_water" in w for w in v.warnings)


def test_validate_offscreen_warns():
    v = validate_scene(_scene(
        steps=[{"tick": 0, "id": "superheroes:roar_wave"}]), CAT)
    assert v.ok
    assert any("offscreen" in w for w in v.warnings)


def test_validate_required_param_missing():
    # a parameterized type whose tuned defaults cannot satisfy the schema
    cat = dict(CAT)
    cat["test:no_defaults"] = {
        "id": "test:no_defaults", "kind": "parameterized_particle",
        "parameterized": True,
        "parameter_schema": {"widget": {"type": "int"}},
        "ready_to_use": True, "factual": {},
    }
    v = validate_scene(_scene(steps=[
        {"tick": 0, "id": "test:no_defaults"}]), cat)
    assert not v.ok
    assert any("widget" in e for e in v.errors)
    # tuned defaults in PARAM_SPECS do satisfy required params
    v2 = validate_scene(_scene(steps=[
        {"tick": 0, "id": "minecraft:dust_color_transition"}]), CAT)
    assert v2.ok, v2.errors


def test_validate_params_ok():
    v = validate_scene(_scene(steps=[
        {"tick": 0, "id": "minecraft:dust_color_transition",
         "options": {"from_color": [1, 0, 0], "to_color": [0, 0, 1],
                     "scale": 2}}]), CAT)
    assert v.ok, v.errors


def test_validate_bad_rgb_param():
    v = validate_scene(_scene(steps=[
        {"tick": 0, "id": "minecraft:dust",
         "options": {"color": "red"}}]), CAT)
    assert not v.ok


def test_validate_bad_angle_and_tick():
    v = validate_scene(_scene(
        camera={"angles": ["sideways"]},
        steps=[{"tick": 99, "id": "minecraft:sonic_boom"}]), CAT)
    assert not v.ok
    assert any("angle" in e for e in v.errors)
    assert any("tick" in e for e in v.errors)


def test_compile_world_event_to_level_event():
    plan, v = compile_scene(_scene(
        steps=[{"tick": 5, "id": "world_event:destroy",
                "pos": [0, 0, -2]}]), CAT, EVENTS)
    assert v.ok, v.errors
    step = plan["steps"][0]
    assert step["at_tick"] == 5
    assert step["pos"] == [0, 0, -2]
    assert step["shot"]["kind"] == "level_event"
    assert step["shot"]["event"] == 2001
    assert step["shot"]["data_block"] == "minecraft:stone"
    assert step["shot"]["resource_id"] == "world_event:destroy"


def test_compile_options_merge_over_tuned_defaults():
    plan, v = compile_scene(_scene(steps=[
        {"tick": 0, "id": "minecraft:sonic_boom",
         "options": {"count": 4}}]), CAT, EVENTS)
    assert v.ok, v.errors
    # tuned default for sonic_boom is count 1; user value wins
    assert plan["steps"][0]["shot"]["options"]["count"] == 4


def test_compile_fx_and_emitter_kinds():
    plan, v = compile_scene(_scene(steps=[
        {"tick": 0, "id": "superheroes:fx_ring"},
        {"tick": 3, "id": "superheroes:roar_wave"}]), CAT, EVENTS)
    assert v.ok, v.errors
    kinds = {s["shot"]["kind"] for s in plan["steps"]}
    assert kinds == {"fx", "quasar_emitter"}
    assert all(s["shot"].get("stop_after") for s in plan["steps"])


def test_compile_steps_sorted_by_tick():
    plan, v = compile_scene(_scene(steps=[
        {"tick": 10, "id": "minecraft:sonic_boom"},
        {"tick": 2, "id": "minecraft:dust"}]), CAT, EVENTS)
    assert v.ok, v.errors
    assert [s["at_tick"] for s in plan["steps"]] == [2, 10]


def test_shot_spec_for_unspawnable_kind():
    shot, reason = shot_spec_for(
        {"id": "x:y", "kind": "mesh", "factual": {}}, EVENTS)
    assert shot is None and reason
