"""VfxProvider contract — pluggable resource sources.

A provider yields *static passports*: identity + factual layer filled from
registry/source data. Measured and visual layers are attached downstream by
the capture and visual-analysis pipelines (keyed by content hash), not by
providers.

Providers must be self-isolating: a broken resource logs a diagnostic and
skips it — one bad resource never fails the whole catalog build. A provider
that cannot run at all (missing artifact) raises ProviderUnavailable so the
catalog can mark the source skipped rather than silently empty.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable

from ..passports.schema import Passport, Provenance


class ProviderUnavailable(Exception):
    """The provider cannot produce anything (artifact/runtime missing)."""


@dataclass
class ProviderResult:
    source: str
    passports: list[Passport] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


class VfxProvider(ABC):
    """Base class for all catalog sources."""

    #: override — short source key stamped on passports, e.g. "photon"
    source: str = "abstract"
    #: bump when extraction logic changes meaningfully → cache invalidation
    provider_version: int = 1

    @abstractmethod
    def extract(self, ctx: "ProviderContext") -> ProviderResult:
        """Produce passports. Raise ProviderUnavailable if the source is absent."""
        ...

    def provenance(self) -> Provenance:
        return Provenance(kind="static-extract",
                          producer=f"{self.source}-provider@{self.provider_version}",
                          at=time.time())


@dataclass
class ProviderContext:
    """Inputs providers can read (artifact dirs, registries dump, config)."""
    data_dir: str            # repo data/ dir
    raw_dir: str             # data/raw — probe artifacts (registries.json, captures index)
    options: dict = field(default_factory=dict)

    def artifact(self, rel_path: str) -> str:
        import os
        return os.path.join(self.raw_dir, rel_path)

    def require_file(self, rel_path: str) -> str:
        import os
        p = self.artifact(rel_path)
        if not os.path.isfile(p):
            raise ProviderUnavailable(f"missing artifact: {rel_path}")
        return p


def collect(provider: VfxProvider, ctx: ProviderContext) -> ProviderResult:
    """Run one provider defensively — convert crashes into a skipped result."""
    try:
        return provider.extract(ctx)
    except ProviderUnavailable as exc:
        return ProviderResult(source=provider.source, skipped=True,
                              skip_reason=str(exc),
                              diagnostics=[f"{provider.source}: unavailable — {exc}"])
    except Exception as exc:  # noqa: BLE001 — provider isolation is the point
        return ProviderResult(source=provider.source, skipped=True,
                              skip_reason=f"crashed: {exc}",
                              diagnostics=[f"{provider.source}: crashed — {type(exc).__name__}: {exc}"])


def collect_all(providers: Iterable[VfxProvider], ctx: ProviderContext) -> list[ProviderResult]:
    return [collect(p, ctx) for p in providers]
