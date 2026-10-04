"""VFX resource passport — layered, honest schema.

Layers (per spec):
  identity   — stable id/source/kind/flags/parameters/provenance/hash
  factual    — objective static data extracted from sources/registry/files
  measured   — objective runtime measurements; absent key = unknown
  visual     — semantic properties with confidence + disagreement flags
  possible_roles — interpretation layer (own confidence), part of `visual`
  diagnostics — extraction problems, never hidden

Truth priority: measured > factual > visual observation > name hints.
`unknown` is expressed by ABSENCE of a key — never by invented defaults;
a measured `false` is a real observation and is kept as `false`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SemanticValue:
    """One visual-semantic property: what independent passes observed."""
    values: list[str]
    confidence: float
    disagreement: bool = False
    evidence: list[str] = field(default_factory=list)  # e.g. ["pass-A", "pass-B"]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"values": list(self.values),
                             "confidence": round(self.confidence, 4)}
        if self.disagreement:
            d["disagreement"] = True
        if self.evidence:
            d["evidence"] = list(self.evidence)
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "SemanticValue":
        return SemanticValue(
            values=[str(v) for v in d.get("values", [])],
            confidence=float(d.get("confidence", 0.0)),
            disagreement=bool(d.get("disagreement", False)),
            evidence=[str(e) for e in d.get("evidence", [])],
        )


@dataclass(frozen=True)
class Provenance:
    """How a piece of the passport was produced."""
    kind: str            # e.g. "static-extract", "capture", "visual-pass-a", "merge"
    producer: str        # provider/tool version, e.g. "photon-provider@1", "probe@0.1"
    at: float            # unix seconds
    detail: str = ""     # optional note (frame set, model version, ...)

    def to_dict(self) -> dict[str, Any]:
        d = {"kind": self.kind, "producer": self.producer, "at": self.at}
        if self.detail:
            d["detail"] = self.detail
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Provenance":
        return Provenance(kind=str(d["kind"]), producer=str(d["producer"]),
                          at=float(d["at"]), detail=str(d.get("detail", "")))


@dataclass
class Passport:
    """Full passport of one visual resource."""
    id: str                      # stable id, e.g. "minecraft:sonic_boom", "photon:fx/fire_ring"
    source: str                  # provider source key, e.g. "minecraft", "photon", "superheroes"
    namespace: str
    kind: str                    # "particle" | "parameterized_particle" | "world_event"
                                 # | "fx" | "emitter" | "trail" | "beam" | "mesh"
                                 # | "material" | "texture" | "shader" | "postfx_graph"
                                 # | "quasar_emitter" | "composite" | ...
    ready_to_use: bool
    primitive: bool              # raw building block vs composed effect
    parameterized: bool = False
    parameter_schema: dict[str, Any] | None = None
    capabilities: list[str] = field(default_factory=list)
    sampled_variants: list[str] = field(default_factory=list)
    factual: dict[str, Any] = field(default_factory=dict)
    measured: dict[str, Any] = field(default_factory=dict)
    visual: dict[str, SemanticValue] = field(default_factory=dict)
    possible_roles: SemanticValue | None = None
    provenance: list[Provenance] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    version: str | None = None       # content version/hash of underlying resource
    schema_version: int = SCHEMA_VERSION

    # ------------------------------------------------------------ serialize

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "id": self.id,
            "source": self.source,
            "namespace": self.namespace,
            "kind": self.kind,
            "ready_to_use": self.ready_to_use,
            "primitive": self.primitive,
            "parameterized": self.parameterized,
        }
        if self.parameter_schema is not None:
            d["parameter_schema"] = self.parameter_schema
        if self.capabilities:
            d["capabilities"] = list(self.capabilities)
        if self.sampled_variants:
            d["sampled_variants"] = list(self.sampled_variants)
        if self.factual:
            d["factual"] = self.factual
        if self.measured:
            d["measured"] = self.measured
        if self.visual:
            d["visual"] = {k: v.to_dict() for k, v in self.visual.items()}
        if self.possible_roles is not None:
            d["possible_roles"] = self.possible_roles.to_dict()
        if self.provenance:
            d["provenance"] = [p.to_dict() for p in self.provenance]
        if self.diagnostics:
            d["diagnostics"] = list(self.diagnostics)
        if self.version:
            d["version"] = self.version
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Passport":
        return Passport(
            id=str(d["id"]),
            source=str(d["source"]),
            namespace=str(d.get("namespace", d["id"].split(":")[0])),
            kind=str(d["kind"]),
            ready_to_use=bool(d.get("ready_to_use", False)),
            primitive=bool(d.get("primitive", False)),
            parameterized=bool(d.get("parameterized", False)),
            parameter_schema=d.get("parameter_schema"),
            capabilities=[str(c) for c in d.get("capabilities", [])],
            sampled_variants=[str(s) for s in d.get("sampled_variants", [])],
            factual=dict(d.get("factual", {})),
            measured=dict(d.get("measured", {})),
            visual={k: SemanticValue.from_dict(v)
                    for k, v in (d.get("visual") or {}).items()},
            possible_roles=(SemanticValue.from_dict(d["possible_roles"])
                            if d.get("possible_roles") else None),
            provenance=[Provenance.from_dict(p)
                        for p in d.get("provenance", [])],
            diagnostics=[str(x) for x in d.get("diagnostics", [])],
            version=d.get("version"),
            schema_version=int(d.get("schema_version", SCHEMA_VERSION)),
        )

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=1)

    # ------------------------------------------------------------- hashing

    def content_hash(self) -> str:
        """Stable hash over identity + factual content (not measured/visual).

        Drives the layered cache: changing factual data re-keys downstream
        stages; measured/visual layers are keyed separately upstream of this.
        """
        payload = {
            "id": self.id, "source": self.source, "kind": self.kind,
            "parameterized": self.parameterized,
            "parameter_schema": self.parameter_schema,
            "capabilities": sorted(self.capabilities),
            "factual": self.factual, "version": self.version,
        }
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]

    def brief_hash(self) -> str:
        """Hash over everything `jev_brief` emits — identity + factual +
        measured + visual + roles. Drives the query-cache fingerprint so
        re-enrichment invalidates cached rankings."""
        blob = json.dumps(self.jev_brief(), ensure_ascii=False,
                          sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]

    # ---------------------------------------------------------- jev briefs

    def jev_brief(self) -> dict[str, Any]:
        """Compact projection sent to Jev inside `state` (token discipline)."""
        brief: dict[str, Any] = {
            "id": self.id, "kind": self.kind, "source": self.source,
            "ready_to_use": self.ready_to_use,
            "parameterized": self.parameterized,
        }
        if self.parameter_schema:
            brief["parameters"] = self.parameter_schema
        if self.capabilities:
            brief["capabilities"] = self.capabilities
        if self.factual:
            brief["facts"] = self.factual
        if self.measured:
            brief["measured"] = self.measured
        if self.visual:
            brief["visual"] = {
                k: {"values": v.values, "confidence": round(v.confidence, 2),
                    **({"disagreement": True} if v.disagreement else {})}
                for k, v in self.visual.items()
            }
        if self.possible_roles and self.possible_roles.values:
            brief["possible_roles"] = {
                "values": self.possible_roles.values,
                "confidence": round(self.possible_roles.confidence, 2),
            }
        return brief

    def one_line(self) -> str:
        """One-line descriptor for Choice criteria text."""
        bits = [self.kind]
        roles = (self.possible_roles.values[:3]
                 if self.possible_roles else [])
        if roles:
            bits.append("/".join(roles))
        shape = self.visual.get("shape")
        if shape and shape.values:
            bits.append("shape=" + "/".join(shape.values[:2]))
        motion = self.visual.get("motion")
        if motion and motion.values:
            bits.append("motion=" + "/".join(motion.values[:2]))
        return f"{self.id}: " + ", ".join(bits)
