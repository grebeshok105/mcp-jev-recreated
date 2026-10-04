"""Veil/Quasar + modded VFX assets -> passports.

Emitters are spawnable composite effects (quasar_emitter, ready_to_use);
particle defs are the primitive building blocks emitters reference;
vfx_params are Codex's per-ability VFX bundles; particle/vfx textures are
materials.
"""
from __future__ import annotations

import json

from ..passports.schema import Passport
from .base import ProviderContext, ProviderResult, VfxProvider


def _asset_id(path: str, keep_dir: str | None = None) -> str:
    """superheroes:quasar/emitters/x.json -> superheroes:x (or superheroes:dir/x)."""
    ns, rest = path.split(":", 1)
    leaf = rest.rsplit("/", 1)[-1]
    if "." in leaf:
        leaf = leaf.rsplit(".", 1)[0]
    if keep_dir:
        return f"{ns}:{keep_dir}/{leaf}"
    return f"{ns}:{leaf}"


class QuasarProvider(VfxProvider):
    source = "quasar"
    provider_version = 1

    def extract(self, ctx: ProviderContext) -> ProviderResult:
        index_path = ctx.require_file("capture/dump/resource_index.json")
        index = json.load(open(index_path))
        out = ProviderResult(source=self.source)
        prov = self.provenance()

        def add(path, kind, ready, primitive, caps=None, extra=None,
                keep_dir: str | None = None):
            try:
                aid = _asset_id(path, keep_dir)
                p = Passport(
                    id=aid, source=self.source, namespace=aid.split(":")[0],
                    kind=kind, ready_to_use=ready, primitive=primitive,
                    capabilities=caps or [],
                    factual={"asset": path, **(extra or {})},
                    provenance=[prov])
                out.passports.append(p)
            except Exception as exc:  # noqa: BLE001
                out.diagnostics.append(f"quasar: {path} skipped — {exc}")

        for path in index.get("quasar_emitters", []):
            add(path, "quasar_emitter", True, False,
                caps=["spawnable", "veil"])
        for path in index.get("particle_defs", []):
            # keep the folder segment: 'minecraft:ash' the particle def is a
            # different resource from 'minecraft:ash' the ParticleType
            add(path, "quasar_particle", True, True, keep_dir="particle_def")
        for path in index.get("vfx_params", []):
            add(path, "composite", True, False, caps=["vfx_bundle"],
                keep_dir="vfx")
        for path in index.get("particle_textures", []):
            add(path, "texture", False, True, caps=["material"],
                extra={"pool": "particle_atlas"}, keep_dir="tex")
        for path in index.get("vfx_textures", []):
            add(path, "texture", False, True, caps=["material"],
                extra={"pool": "vfx"}, keep_dir="tex")
        return out
