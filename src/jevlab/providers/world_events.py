"""Vanilla world events (LevelEvents) -> passports.

The probe dumps every LevelEvents constant with its numeric id. Sound-only
events are still catalogued (they ARE spawnable) but flagged so the selector
can tell visual events from audio ones.
"""
from __future__ import annotations

import json

from ..passports.schema import Passport
from .base import ProviderContext, ProviderResult, VfxProvider


def _capabilities(name: str) -> list[str]:
    caps = []
    if name.startswith("SOUND_") or "_SOUND_" in name:
        caps.append("sound")
    if name.startswith("PARTICLES_") or "PARTICLES_" in name or name.startswith("ANIMATION_"):
        caps.append("particles")
    if name.startswith("ANIMATION_"):
        caps.append("animation")
    if "BLOCK" in name and "PARTICLES" not in name:
        caps.append("block-state")
    return caps or ["misc"]


class WorldEventsProvider(VfxProvider):
    source = "world_events"
    provider_version = 1

    def extract(self, ctx: ProviderContext) -> ProviderResult:
        path = ctx.require_file("capture/dump/level_events.json")
        events = json.load(open(path))["events"]
        out = ProviderResult(source=self.source)
        prov = self.provenance()
        for e in events:
            try:
                name, eid = e["name"], int(e["id"])
                caps = _capabilities(name)
                p = Passport(
                    id=f"minecraft:world_event/{name}",
                    source=self.source, namespace="minecraft",
                    kind="world_event",
                    ready_to_use=True, primitive=True,
                    parameterized=("PARTICLES_DESTROY_BLOCK" == name or
                                   name in ("PARTICLES_AND_SOUND_BRUSH_BLOCK_COMPLETE",
                                            "ANIMATION_SMASH_ATTACK")),
                    factual={
                        "event_id": eid,
                        "event_name": name,
                        "has_visual": "particles" in caps or "animation" in caps,
                        "data_note": ("event data = block state id"
                                      if "BLOCK" in name or eid == 2001
                                      else "event data usually 0"),
                    },
                    capabilities=caps,
                    provenance=[prov],
                )
                out.passports.append(p)
            except Exception as exc:  # noqa: BLE001
                out.diagnostics.append(f"world_events: skipped {e} — {exc}")
        return out
