"""Photon resources -> passports: .fx effects, meshes, shaders, texture pool.

Sources: the probe's photon registry dump plus the modpack resource index.
`photon_textures` in the index is the full texture pool Photon can bind as
materials — every vanilla/mod block+item texture. They are catalogued as
primitive materials (ready_to_use=False: not standalone effects).
"""
from __future__ import annotations

import json

from ..passports.schema import Passport
from .base import ProviderContext, ProviderResult, VfxProvider


def _shader_kind(path: str) -> str:
    leaf = path.rsplit("/", 1)[-1]
    if any(k in leaf for k in ("bloom", "post", "blur", "fxaa", "motion",
                               "scatter", "downsample", "upsample", "composite")):
        return "postfx_graph"
    return "shader"


class PhotonProvider(VfxProvider):
    source = "photon"
    provider_version = 1

    def extract(self, ctx: ProviderContext) -> ProviderResult:
        photon_path = ctx.require_file("capture/dump/photon.json")
        index_path = ctx.require_file("capture/dump/resource_index.json")
        photon = json.load(open(photon_path))
        index = json.load(open(index_path))
        out = ProviderResult(source=self.source)
        prov = self.provenance()

        for fx_id in photon.get("fx", []):
            try:
                p = Passport(
                    id=fx_id, source=self.source,
                    namespace=fx_id.split(":")[0],
                    kind="fx",
                    ready_to_use=True, primitive=False,
                    factual={"container": "photon_fx", "format": "gzipped NBT"},
                    provenance=[prov],
                )
                out.passports.append(p)
            except Exception as exc:  # noqa: BLE001
                out.diagnostics.append(f"photon: fx {fx_id} skipped — {exc}")

        for path in index.get("photon_models", []):
            try:
                ns = path.split(":")[0]
                out.passports.append(Passport(
                    id=f"photon:mesh/{path}", source=self.source, namespace=ns,
                    kind="mesh", ready_to_use=True, primitive=True,
                    factual={"asset": path, "format": path.rsplit(".", 1)[-1]},
                    provenance=[prov]))
            except Exception as exc:  # noqa: BLE001
                out.diagnostics.append(f"photon: mesh {path} skipped — {exc}")

        for path in index.get("photon_shaders", []):
            try:
                ns = path.split(":")[0]
                out.passports.append(Passport(
                    id=f"photon:shader/{path}", source=self.source, namespace=ns,
                    kind=_shader_kind(path), ready_to_use=True, primitive=True,
                    factual={"asset": path},
                    provenance=[prov]))
            except Exception as exc:  # noqa: BLE001
                out.diagnostics.append(f"photon: shader {path} skipped — {exc}")

        for path in index.get("photon_textures", []):
            try:
                ns = path.split(":")[0]
                out.passports.append(Passport(
                    id=f"photon:texture/{path}", source=self.source, namespace=ns,
                    kind="texture", ready_to_use=False, primitive=True,
                    capabilities=["material"],
                    factual={"asset": path, "pool": "photon_materials"},
                    provenance=[prov]))
            except Exception as exc:  # noqa: BLE001
                out.diagnostics.append(f"photon: texture {path} skipped — {exc}")
        return out
