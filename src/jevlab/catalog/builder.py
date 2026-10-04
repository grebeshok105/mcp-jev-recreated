"""Catalog assembly — run providers, dedupe, merge enrichment layers."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..passports.schema import Passport, SemanticValue
from ..providers.base import ProviderContext, ProviderResult, VfxProvider, collect_all


@dataclass
class CatalogStats:
    total: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    by_kind: dict[str, int] = field(default_factory=dict)
    parameterized: int = 0
    primitives: int = 0
    with_measured: int = 0
    with_visual: int = 0
    disagreements: int = 0
    failed_sources: list[str] = field(default_factory=list)


@dataclass
class Catalog:
    resources: dict[str, Passport]
    diagnostics: list[str] = field(default_factory=list)
    built_at: float = field(default_factory=time.time)
    stats: CatalogStats = field(default_factory=CatalogStats)

    def recompute_stats(self) -> CatalogStats:
        s = CatalogStats(total=len(self.resources))
        for p in self.resources.values():
            s.by_source[p.source] = s.by_source.get(p.source, 0) + 1
            s.by_kind[p.kind] = s.by_kind.get(p.kind, 0) + 1
            s.parameterized += 1 if p.parameterized else 0
            s.primitives += 1 if p.primitive else 0
            s.with_measured += 1 if p.measured else 0
            s.with_visual += 1 if p.visual else 0
            s.disagreements += 1 if any(
                v.disagreement for v in p.visual.values()) else 0
        self.stats = s
        return s

    def get(self, resource_id: str) -> Passport | None:
        return self.resources.get(resource_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "built_at": self.built_at,
            "stats": {
                "total": self.stats.total,
                "by_source": self.stats.by_source,
                "by_kind": self.stats.by_kind,
                "parameterized": self.stats.parameterized,
                "primitives": self.stats.primitives,
                "with_measured": self.stats.with_measured,
                "with_visual": self.stats.with_visual,
                "disagreements": self.stats.disagreements,
            },
            "diagnostics": self.diagnostics,
            "resources": [p.to_dict() for p in
                          sorted(self.resources.values(), key=lambda p: p.id)],
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Catalog":
        cat = Catalog(resources={})
        cat.built_at = float(d.get("built_at", 0.0))
        cat.diagnostics = [str(x) for x in d.get("diagnostics", [])]
        for r in d.get("resources", []):
            p = Passport.from_dict(r)
            cat.resources[p.id] = p
        cat.recompute_stats()
        return cat

    def save(self, path: str) -> None:
        self.recompute_stats()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    @staticmethod
    def load(path: str) -> "Catalog":
        with open(path, encoding="utf-8") as fh:
            return Catalog.from_dict(json.load(fh))


class CatalogBuilder:
    def __init__(self, providers: Iterable[VfxProvider]):
        self.providers = list(providers)

    def build(self, ctx: ProviderContext) -> Catalog:
        results = collect_all(self.providers, ctx)
        catalog = Catalog(resources={})
        seen: dict[str, str] = {}
        for res in results:
            for d in res.diagnostics:
                catalog.diagnostics.append(d)
            for passport in res.passports:
                if passport.id in catalog.resources:
                    catalog.diagnostics.append(
                        f"dedupe: {passport.id} claimed by {passport.source} "
                        f"and {seen[passport.id]} — keeping first")
                    continue
                catalog.resources[passport.id] = passport
                seen[passport.id] = passport.source
        catalog.recompute_stats()
        catalog.stats.failed_sources = [
            r.source for r in results if r.skipped]
        return catalog

    # ----------------------------------------------------- enrichment merge

    @staticmethod
    def merge_measured(catalog: Catalog, resource_id: str,
                       measured: dict[str, Any]) -> bool:
        p = catalog.resources.get(resource_id)
        if p is None:
            return False
        p.measured.update(measured)
        return True

    @staticmethod
    def merge_visual(catalog: Catalog, resource_id: str,
                     visual: dict[str, SemanticValue],
                     possible_roles: SemanticValue | None = None) -> bool:
        p = catalog.resources.get(resource_id)
        if p is None:
            return False
        p.visual.update(visual)
        if possible_roles is not None:
            p.possible_roles = possible_roles
        return True
