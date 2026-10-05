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


# ------------------------------------------------------------------ safety

def test_patch_stock_refused(tmp_path, monkeypatch):
    """patch_fx must refuse resources without provenance (stock fixtures)."""
    real_src = fx_edit.FX_SRC_DIR
    monkeypatch.setattr(fx_edit, "FX_SRC_DIR", str(tmp_path))
    monkeypatch.setattr(fx_edit, "FX_RUNTIME_DIR", str(tmp_path / "rt"))
    monkeypatch.setattr(fx_edit, "PROVENANCE_DIR", str(tmp_path / "prov"))
    import shutil, os
    os.makedirs(tmp_path / "vfxlab/fx", exist_ok=True)
    shutil.copyfile(os.path.join(real_src, "vfxlab/fx/laser_beam.fx"),
                    str(tmp_path / "vfxlab/fx/laser_beam.fx"))
    p = fx_edit.patch_fx("vfxlab:laser_beam", [
        {"op": "scalar", "emitter": "0", "field": "duration", "value": 1}])
    assert not p["ok"]
    assert "not a clone" in p["errors"][0]


def test_patch_allow_stock_bypasses_guard(tmp_path, monkeypatch):
    real_src = fx_edit.FX_SRC_DIR
    monkeypatch.setattr(fx_edit, "FX_SRC_DIR", str(tmp_path))
    monkeypatch.setattr(fx_edit, "FX_RUNTIME_DIR", str(tmp_path / "rt"))
    monkeypatch.setattr(fx_edit, "PROVENANCE_DIR", str(tmp_path / "prov"))
    import shutil, os
    os.makedirs(tmp_path / "vfxlab/fx", exist_ok=True)
    shutil.copyfile(os.path.join(real_src, "vfxlab/fx/laser_beam.fx"),
                    str(tmp_path / "vfxlab/fx/laser_beam.fx"))
    p = fx_edit.patch_fx("vfxlab:laser_beam", [
        {"op": "scalar", "emitter": "0", "field": "duration", "value": 1}],
        allow_stock=True)
    assert p["ok"], p


def test_patch_error_leaves_file_untouched(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:laser_beam", "vfxlab:b6", monkeypatch)
    path = fx_edit.fx_file_path("vfxlab:b6")
    before = open(path, "rb").read()
    p = fx_edit.patch_fx("vfxlab:b6", [
        {"op": "scalar", "emitter": "0", "field": "duration", "value": -5}])
    assert not p["ok"]
    assert open(path, "rb").read() == before


def test_enum_domain_checked(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:laser_beam", "vfxlab:b7", monkeypatch)
    bad = fx_edit.patch_fx("vfxlab:b7", [
        {"op": "scalar", "emitter": "0", "field": "renderer.layer",
         "value": "Bogus"}])
    assert not bad["ok"]
    assert "not in" in bad["errors"][0]
    good = fx_edit.patch_fx("vfxlab:b7", [
        {"op": "scalar", "emitter": "0", "field": "renderer.layer",
         "value": "Opaque"}])
    assert good["ok"], good


def test_bounds_checked(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:ember_ring_burst",
                 "vfxlab:eb3", monkeypatch)
    p = fx_edit.patch_fx("vfxlab:eb3", [
        {"op": "scalar", "emitter": "0",
         "field": "emission.bursts.payload[0].interval", "value": 0}])
    assert not p["ok"]
    assert "outside" in p["errors"][0]


def test_bool_and_fractional_rejected(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:laser_beam", "vfxlab:b8", monkeypatch)
    p = fx_edit.patch_fx("vfxlab:b8", [
        {"op": "scalar", "emitter": "0", "field": "duration", "value": True},
        {"op": "scalar", "emitter": "0", "field": "duration", "value": 2.5}])
    assert not p["ok"]
    assert len(p["errors"]) == 2


def test_color_alpha_prefix(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:laser_beam", "vfxlab:b9", monkeypatch)
    p = fx_edit.patch_fx("vfxlab:b9", [
        {"op": "color", "emitter": "0", "field": "color",
         "value": "#80FF0000"}])
    assert p["ok"], p
    i = fx_edit.inspect_fx("vfxlab:b9")
    assert i["emitters"][0]["fields"]["color"]["value"] == "#80ff0000"


def test_dig_refuses_numfunc_interior_and_underscore(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:laser_beam", "vfxlab:b10", monkeypatch)
    p = fx_edit.patch_fx("vfxlab:b10", [
        {"op": "scalar", "emitter": "0", "field": "color.data.number",
         "value": 5},
        {"op": "scalar", "emitter": "0", "field": "lights._enable",
         "value": 0}])
    assert not p["ok"]
    assert len(p["errors"]) == 2


def test_malformed_ops_error_not_crash(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:laser_beam", "vfxlab:b11", monkeypatch)
    p = fx_edit.patch_fx("vfxlab:b11", [
        "not a dict",
        {"op": "scalar", "emitter": "0"},          # missing field+value
        {"op": "frobnicate", "emitter": "0", "field": "width", "value": 1},
    ])
    assert not p["ok"]
    assert len(p["errors"]) == 3


def test_bad_id_and_prov_filename_collision(tmp_path, monkeypatch):
    _fresh_clone(tmp_path, "vfxlab:laser_beam", "vfxlab:a_b_c", monkeypatch)
    fx_edit.clone_fx("vfxlab:laser_beam", "vfxlab:a_b:c")
    assert fx_edit._prov_path("vfxlab:a_b_c", legacy_ok=False) != \
        fx_edit._prov_path("vfxlab:a_b:c", legacy_ok=False)
    assert not fx_edit.clone_fx("vfxlab:laser_beam", "vfxlab:../x")["ok"]
    assert not fx_edit.clone_fx("vfxlab:laser_beam", "vfxlab:/x")["ok"]


# ------------------------------------------------- multi-emitter synthetic

def _make_multi(tmp_path):
    """2-emitter fixture: o1 child of o0, config string ref to o0's id."""
    import copy
    from jevlab.fx_nbt import Tag, TAG_LIST, TAG_STRING
    name, root = load_fx(_path("laser_beam"))
    objs = fx_edit._objects(root)
    o1 = copy.deepcopy(objs.value[0])
    t0 = objs.value[0].get("data").get("transform").get("id").value
    d1, tr1 = o1.get("data"), o1.get("data").get("transform")
    tr1.get("id").value = "uuid-child"
    tr1.get("_parentId").value = t0
    d1.get("config").set("customSpace", Tag(TAG_STRING, t0))
    tr0 = objs.value[0].get("data").get("transform")
    tr0.set("_childrenId", Tag(TAG_LIST, [Tag(TAG_STRING, "uuid-child")]))
    objs.value.append(o1)
    return name, root, t0


def test_clone_remaps_transform_ids(tmp_path, monkeypatch):
    name, root, t0 = _make_multi(tmp_path)
    objs = fx_edit._objects(root)
    fx_edit._remap_transform_ids(root)
    ids = [o.get("data").get("transform").get("id").value
           for o in objs.value]
    assert t0 not in ids and "uuid-child" not in ids
    o1d = objs.value[1].get("data")
    # parent ref + config ref now point at the NEW parent id
    assert o1d.get("transform").get("_parentId").value == ids[0]
    assert o1d.get("config").get("customSpace").value == ids[0]
    ch = objs.value[0].get("data").get("transform").get("_childrenId")
    assert ch.value[0].value == ids[1]


def test_emitter_removal_scrubs_all_refs(tmp_path, monkeypatch):
    name, root, t0 = _make_multi(tmp_path)  # built from the real fixture
    monkeypatch.setattr(fx_edit, "FX_SRC_DIR", str(tmp_path))
    monkeypatch.setattr(fx_edit, "FX_RUNTIME_DIR", str(tmp_path / "rt"))
    monkeypatch.setattr(fx_edit, "PROVENANCE_DIR", str(tmp_path / "prov"))
    import os
    os.makedirs(tmp_path / "vfxlab/fx", exist_ok=True)
    save_fx(str(tmp_path / "vfxlab/fx/multi.fx"), name, root)
    r = fx_edit.clone_fx("vfxlab:multi", "vfxlab:multi2")
    assert r["ok"], r
    p = fx_edit.patch_fx("vfxlab:multi2", [
        {"op": "toggle", "emitter": "emitter:0", "value": False}])
    assert p["ok"], p
    _, root2 = load_fx(str(tmp_path / "vfxlab/fx/multi2.fx"))
    objs2 = fx_edit._objects(root2)
    assert len(objs2.value) == 1
    surv = objs2.value[0].get("data")
    # surviving emitter was the child: parent ref + config ref scrubbed
    assert surv.get("transform").get("_parentId").value == "_NULL_"
    assert surv.get("config").get("customSpace").value == "_NULL_"


# ------------------------------------------------------------------ codec

def test_empty_list_elem_type_preserved():
    from jevlab.fx_nbt import Tag, TAG_INT, loads
    t = Tag(TAG_COMPOUND, [("xs", Tag(TAG_LIST, [], TAG_INT))])
    raw = dumps("", t)
    _, back = loads(raw)
    xs = back.get("xs")
    assert xs.elem_type == TAG_INT
    # and re-encode keeps TAG_INT, not TAG_END
    assert dumps("", back) == raw


def test_validate_non_list_fxobjects(tmp_path, monkeypatch):
    import gzip
    from jevlab.fx_nbt import Tag, TAG_COMPOUND, TAG_INT
    root = Tag(TAG_COMPOUND, [
        ("version", Tag(TAG_INT, 1)),
        ("fxData", Tag(TAG_COMPOUND, [
            ("fxObjects", Tag(TAG_INT, 5))]))])
    monkeypatch.setattr(fx_edit, "FX_SRC_DIR", str(tmp_path))
    monkeypatch.setattr(fx_edit, "FX_RUNTIME_DIR", str(tmp_path / "rt"))
    os.makedirs(tmp_path / "vfxlab/fx", exist_ok=True)
    import gzip as gz
    with gz.open(str(tmp_path / "vfxlab/fx/bad.fx"), "wb") as f:
        f.write(dumps("", root))
    v = fx_edit.validate_fx("vfxlab:bad")
    assert not v["ok"]
    assert "not a list" in v["errors"][0]


# ------------------------------------------------------------------ register

def test_register_updates_stats_and_passport(tmp_path, monkeypatch):
    import json as js
    real_cat = fx_edit.CATALOG
    _fresh_clone(tmp_path, "vfxlab:laser_beam",
                 "vfxlab:reg1", monkeypatch)
    import shutil
    shutil.copyfile(real_cat, str(tmp_path / "catalog.json"))
    cat0 = js.load(open(str(tmp_path / "catalog.json")))
    n0 = cat0["stats"]["total"]
    r = fx_edit.register_fx("vfxlab:reg1")
    assert r["ok"], r
    cat1 = js.load(open(str(tmp_path / "catalog.json")))
    assert cat1["stats"]["total"] == n0 + 1
    assert cat1["stats"]["by_kind"]["fx"] == \
        cat0["stats"]["by_kind"].get("fx", 0) + 1
    res = next(x for x in cat1["resources"] if x["id"] == "vfxlab:reg1")
    # clone must not claim the source's captured look
    assert res["visual_status"] == "inherited"
    assert "measured" not in res
    assert "visual" not in res
