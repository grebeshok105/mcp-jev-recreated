"""Unit tests for jevlab.fx_nbt round-trip and jevlab.fx_edit ops."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest

from jevlab.fx_nbt import (Tag, TAG_COMPOUND, TAG_INT, TAG_LIST, TAG_STRING,
                         dumps, load_fx, loads, save_fx)
from jevlab import fx_edit

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "..",
                           "probe/src/main/resources/assets")
FIXTURES = ["ember_ring_burst", "laser_beam", "ribbon_trail",
            "smoke_plume", "sparkle_sphere"]


def _path(name):
    return fx_edit.fx_file_path(f"vfxlab:{name}")


def _tree_eq(a: Tag, b: Tag) -> bool:
    if a.type != b.type:
        return False
    if a.type == TAG_COMPOUND:
        if [n for n, _ in a.value] != [n for n, _ in b.value]:
            return False
        return all(_tree_eq(ta, tb) for (_, ta), (_, tb)
                   in zip(a.value, b.value))
    if a.type == TAG_LIST:
        return (len(a.value) == len(b.value)
                and all(_tree_eq(ta, tb) for ta, tb in zip(a.value, b.value)))
    return a.value == b.value


# ------------------------------------------------------------------ nbt

@pytest.mark.parametrize("name", FIXTURES)
def test_roundtrip_byte_identical(name):
    import gzip
    path = _path(name)
    raw = gzip.open(path, "rb").read()
    name_, root = loads(raw)
    assert dumps(name_, root) == raw


def test_roundtrip_tree_eq():
    _, root = load_fx(_path("laser_beam"))
    _, root2 = loads(dumps("", root))
    assert _tree_eq(root, root2)


# ------------------------------------------------------------------ inspect

def test_inspect_laser_beam():
    r = fx_edit.inspect_fx("vfxlab:laser_beam")
    assert r["ok"]
    e = r["emitters"][0]
    assert e["type"] == "beam_emitter"
    f = e["fields"]
    assert f["color"]["value"] == "#ff33ccff"
    assert f["color"]["patchable"] == "color"
    assert f["width"]["value"] == pytest.approx(0.12)
    assert f["duration"]["value"] == 120
    assert f["end"]["value"] == [4.0, 0.5, 0.0]
    assert e["layers"]["lights"]["enabled"] is True
    assert "gradient" not in json_fields(e)


def json_fields(e):
    return set(e["fields"])


def test_inspect_missing_id():
    r = fx_edit.inspect_fx("vfxlab:nope_not_a_fx")
    assert not r["ok"]


def test_inspect_burst_payload_fields():
    r = fx_edit.inspect_fx("vfxlab:ember_ring_burst")
    f = r["emitters"][0]["fields"]
    assert f["emission.bursts.payload[0].count"]["value"] == 60
    assert f["emission.bursts.payload[0].probability"]["value"] == 1.0


# ------------------------------------------------------------------ ops

def _fresh_clone(tmp_path, src, new, monkeypatch):
    import shutil
    real_src = fx_edit.FX_SRC_DIR
    monkeypatch.setattr(fx_edit, "FX_SRC_DIR", str(tmp_path))
    monkeypatch.setattr(fx_edit, "FX_RUNTIME_DIR", str(tmp_path / "rt"))
    monkeypatch.setattr(fx_edit, "PROVENANCE_DIR", str(tmp_path / "prov"))
    monkeypatch.setattr(fx_edit, "CATALOG", str(tmp_path / "catalog.json"))
    os.makedirs(tmp_path / "vfxlab/fx", exist_ok=True)
    for f in FIXTURES:
        shutil.copyfile(os.path.join(real_src, "vfxlab/fx", f"{f}.fx"),
                        str(tmp_path / "vfxlab/fx" / f"{f}.fx"))
    return fx_edit.clone_fx(src, new)


def test_clone_then_scalar_and_color(tmp_path, monkeypatch):
    r = _fresh_clone(tmp_path, "vfxlab:laser_beam",
                     "vfxlab:beam2", monkeypatch)
    assert r["ok"], r
    p = fx_edit.patch_fx("vfxlab:beam2", [
        {"op": "scalar", "emitter": "0", "field": "width", "value": 0.5},
        {"op": "color", "emitter": "0", "field": "color", "value": "#FF0000"},
        {"op": "scalar", "emitter": "0", "field": "end",
         "value": [2.0, 0.5, 1.0]},
        {"op": "toggle", "emitter": "0", "field": "lights", "value": False},
    ])
    assert p["ok"], p
    i = fx_edit.inspect_fx("vfxlab:beam2")
    f = i["emitters"][0]["fields"]
    assert f["width"]["value"] == pytest.approx(0.5)
    assert f["color"]["value"] == "#ffff0000"
    assert f["end"]["value"] == [2.0, 0.5, 1.0]
    assert i["emitters"][0]["layers"]["lights"]["enabled"] is False


def test_patch_refuses_nonconstant(tmp_path, monkeypatch):
    r = _fresh_clone(tmp_path, "vfxlab:ribbon_trail",
                     "vfxlab:rt2", monkeypatch)
    assert r["ok"]
    p = fx_edit.patch_fx("vfxlab:rt2", [
        {"op": "scalar", "emitter": "0",
         "field": "colorOverTrail", "value": 5},
    ])
    assert not p["ok"]
    assert any("not scalar-patchable" in e or "not a constant"
               in e for e in p["errors"])


def test_patch_unknown_field_errors(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:laser_beam", "vfxlab:b3", monkeypatch)
    p = fx_edit.patch_fx("vfxlab:b3", [
        {"op": "scalar", "emitter": "0", "field": "nope", "value": 1}])
    assert not p["ok"]
    assert "no field 'nope'" in p["errors"][0]


def test_toggle_emitter_refuses_single_object(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:laser_beam", "vfxlab:b4", monkeypatch)
    p = fx_edit.patch_fx("vfxlab:b4", [
        {"op": "toggle", "emitter": "emitter:0", "value": False}])
    assert not p["ok"]
    assert "only emitter" in p["errors"][0]


def test_clone_never_mutates_source(tmp_path, monkeypatch):
    import gzip, hashlib
    before = hashlib.sha256(
        gzip.open(_path("laser_beam"), "rb").read()).hexdigest()
    _fresh_clone(tmp_path, "vfxlab:laser_beam", "vfxlab:b5", monkeypatch)
    fx_edit.patch_fx("vfxlab:b5", [
        {"op": "color", "emitter": "0", "field": "color",
         "value": "#00FF00"}])
    after = hashlib.sha256(
        gzip.open(_path("laser_beam"), "rb").read()).hexdigest()
    assert before == after


def test_burst_probability_toggle(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:ember_ring_burst",
                 "vfxlab:eb2", monkeypatch)
    p = fx_edit.patch_fx("vfxlab:eb2", [
        {"op": "scalar", "emitter": "0",
         "field": "emission.bursts.payload[0].probability", "value": 0.0}])
    assert p["ok"]
    i = fx_edit.inspect_fx("vfxlab:eb2")
    assert i["emitters"][0]["fields"][
        "emission.bursts.payload[0].probability"]["value"] == 0.0


# ------------------------------------------------------------------ validate

def test_validate_stock():
    v = fx_edit.validate_fx("vfxlab:laser_beam")
    assert v["ok"]
    assert v["emitters"] == 1
