"""Runtime-registered particle types -> passports (vanilla + modded alike).

Reads the probe's live registry dump: every ParticleType actually registered
in the running client (142 on the current box: 109 minecraft + 33 superheroes).
Parameterized types carry a real parameter schema where the codec is known;
others are marked parameterized with an opaque schema note instead of
inventing fields.
"""
from __future__ import annotations

import json
from typing import Any

from ..passports.schema import Passport
from .base import ProviderContext, ProviderResult, VfxProvider

#: Known ParticleOptions codecs — real fields, from the 1.21.1 codecs.
PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "minecraft:dust": {
        "color": {"type": "rgb", "default": [1.0, 0.0, 0.0]},
        "scale": {"type": "float", "min": 0.01, "max": 4.0, "default": 1.0},
    },
    "minecraft:dust_color_transition": {
        "from_color": {"type": "rgb"}, "to_color": {"type": "rgb"},
        "scale": {"type": "float", "min": 0.01, "max": 4.0},
    },
    "minecraft:sculk_charge": {"roll": {"type": "float", "unit": "radians"}},
    "minecraft:shriek": {"delay": {"type": "int", "unit": "ticks"}},
    "minecraft:vibration": {"destination": {"type": "position_source"},
                            "arrival_in_ticks": {"type": "int"}},
    "minecraft:block": {"block_state": {"type": "blockstate"}},
    "minecraft:block_marker": {"block_state": {"type": "blockstate"}},
    "minecraft:falling_dust": {"block_state": {"type": "blockstate"}},
    "minecraft:dust_pillar": {"block_state": {"type": "blockstate"}},
    "minecraft:item": {"item": {"type": "itemstack"}},
    "minecraft:entity_effect": {"color": {"type": "argb"}},
}


class ParticleTypesProvider(VfxProvider):
    source = "particles"
    provider_version = 1

    def extract(self, ctx: ProviderContext) -> ProviderResult:
        types_path = ctx.require_file("capture/dump/particle_types.json")
        providers_path = ctx.require_file("capture/dump/particle_providers.json")
        types = json.load(open(types_path))["types"]
        factories = {p["id"]: p["factory"]
                     for p in json.load(open(providers_path))["providers"]}
        out = ProviderResult(source=self.source)
        prov = self.provenance()
        for t in types:
            try:
                rid = t["id"]
                parameterized = bool(t["parameterized"])
                p = Passport(
                    id=rid, source=self.source,
                    namespace=t.get("namespace", rid.split(":")[0]),
                    kind=("parameterized_particle" if parameterized else "particle"),
                    ready_to_use=True, primitive=True,
                    parameterized=parameterized,
                    parameter_schema=PARAM_SCHEMAS.get(rid),
                    factual={"class": t["class"]},
                    provenance=[prov],
                )
                if rid in factories:
                    p.factual["client_factory"] = factories[rid]
                if parameterized and rid not in PARAM_SCHEMAS:
                    p.factual["parameter_schema_note"] = (
                        "parameterized type, codec not enumerated — "
                        "parameters required but schema unknown")
                out.passports.append(p)
            except Exception as exc:  # noqa: BLE001
                out.diagnostics.append(
                    f"particles: skipped {t.get('id', '?')} — {exc}")
        return out
