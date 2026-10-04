"""Visual layer: merge independent observation passes into `visual`.

Each pass reports per-shot properties as key -> list of observed values plus
a free-form description, visibility, and possible_roles. Merging keeps the
union of values per key; a key where passes report disjoint value sets is
flagged `disagreement` (the honest signal, never averaged away).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from ..catalog.builder import CatalogBuilder
from ..passports.schema import SemanticValue
from .measured import shot_resource_id

_KIND_KEYS = ("dominant_colors", "shape", "motion", "brightness", "density",
              "scale_impression", "persistence", "texture_quality",
              "blend_appearance")

_STOPWORDS = frozenset({
    "a", "an", "the", "at", "by", "of", "in", "on", "to", "and", "or",
    "with", "into", "over", "per", "is", "it", "its", "one", "two",
    "between", "through", "across", "from", "than", "then", "only",
    "very", "quite", "rather", "mostly", "roughly", "about", "around",
    "no", "not", "all", "every", "each", "some", "any",
})


def _tokens(value: str) -> set[str]:
    """Content tokens of one observed value — timing qualifiers and
    connective words stripped so phrasing differences don't fake
    disagreement. Keeps what the pass actually claimed."""
    toks = set()
    for raw in re.findall(r"[a-z]+\d*", value.lower()):
        if raw in _STOPWORDS or re.fullmatch(r"t\d+", raw):
            continue
        toks.add(raw)
        # naive singularization: 'puffs' vs 'puff', 'classes' vs 'class'
        # must not fake a disagreement. Stem forms are unioned so a real
        # divergence (entirely different vocabulary) still flags.
        if len(raw) > 3 and raw.endswith("s"):
            toks.add(raw[:-1])
        if len(raw) > 4 and raw.endswith("es"):
            toks.add(raw[:-2])
    return toks


def merge_passes(pass_outputs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """pass_outputs: list of {"observations": {shot: {...}}} -> per-shot merge."""
    per_shot: dict[str, list[dict[str, Any]]] = {}
    for out in pass_outputs:
        for shot, obs in (out.get("observations") or {}).items():
            per_shot.setdefault(shot, []).append(obs)

    merged: dict[str, dict[str, Any]] = {}
    for shot, obs_list in per_shot.items():
        props: dict[str, list[tuple[str, list[str]]]] = {}
        confs, roles, descs, vis = [], [], [], []
        for i, obs in enumerate(obs_list):
            tag = chr(ord("a") + i)
            for k, vals in (obs.get("properties") or {}).items():
                props.setdefault(k, []).append((tag, [str(v) for v in vals]))
            confs.append(float(obs.get("confidence", 0)))
            roles.extend(str(r) for r in obs.get("possible_roles", []))
            if obs.get("description"):
                descs.append(f"[{tag}] {obs['description']}")
            vis.append(str(obs.get("visibility", "")))
        visual: dict[str, SemanticValue] = {}
        for k, tagged in props.items():
            vals = sorted({v for _, vs in tagged for v in vs})
            # disagreement = passes described the property in fully disjoint
            # terms (no shared content token between any of their values)
            per_pass_toks = []
            for _, vs in tagged:
                toks = set()
                for v in vs:
                    toks |= _tokens(v)
                if toks:
                    per_pass_toks.append(toks)
            disagreement = (len(per_pass_toks) > 1 and
                            any(s.isdisjoint(o)
                                for i, s in enumerate(per_pass_toks)
                                for o in per_pass_toks[i + 1:]))
            visual[k] = SemanticValue(
                values=vals,
                confidence=round(sum(confs) / max(len(confs), 1), 4),
                disagreement=disagreement,
                evidence=[t for t, _ in tagged])
        if descs:
            visual["description"] = SemanticValue(
                values=descs, confidence=round(sum(confs) / max(len(confs), 1), 4),
                evidence=[chr(ord("a") + i) for i in range(len(obs_list))])
        if vis and any(v != vis[0] for v in vis):
            visual["visibility"] = SemanticValue(
                values=sorted(set(vis)), confidence=0.5, disagreement=True,
                evidence=[chr(ord("a") + i) for i in range(len(vis))])
        merged[shot] = {
            "visual": visual,
            "possible_roles": SemanticValue(
                values=sorted(set(roles)),
                confidence=round(sum(confs) / max(len(confs), 1), 4),
                evidence=[chr(ord("a") + i) for i in range(len(obs_list))])
            if roles else None,
        }
    return merged


def apply_visual(catalog, pass_files: list[str]) -> list[str]:
    diags: list[str] = []
    pass_outputs = []
    for f in pass_files:
        if not os.path.isfile(f):
            diags.append(f"visual: pass file missing {f}")
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                pass_outputs.append(json.load(fh))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            diags.append(f"visual: pass file unreadable {f}: {exc}")
    if not pass_outputs:
        return diags + ["visual: no pass outputs loaded"]
    for shot, m in merge_passes(pass_outputs).items():
        rid = shot_resource_id(shot)
        if catalog.get(rid) is None:
            diags.append(f"visual: shot {shot} -> {rid} has no passport")
            continue
        try:
            CatalogBuilder.merge_visual(catalog, rid, m["visual"],
                                        m.get("possible_roles"))
        except Exception as exc:  # one broken shot never breaks the build
            diags.append(f"visual: merge failed for {shot} -> {rid}: {exc}")
    return diags
