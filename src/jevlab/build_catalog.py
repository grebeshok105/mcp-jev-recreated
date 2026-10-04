"""Build the VFX catalog from probe artifacts.

Usage:
    python -m jevlab.build_catalog [--data-dir data] [--out data/catalog.json]
                                   [--visual-pass file ...]
"""
from __future__ import annotations

import argparse
import os

from .catalog.builder import CatalogBuilder
from .enrichment.measured import apply_measured
from .enrichment.visual import apply_visual
from .providers.base import ProviderContext
from .providers.particles import ParticleTypesProvider
from .providers.photon import PhotonProvider
from .providers.quasar import QuasarProvider
from .providers.world_events import WorldEventsProvider


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default=None)
    ap.add_argument("--visual-pass", action="append", default=[])
    args = ap.parse_args()

    ctx = ProviderContext(data_dir=args.data_dir, raw_dir=args.data_dir)
    builder = CatalogBuilder([
        ParticleTypesProvider(), WorldEventsProvider(),
        PhotonProvider(), QuasarProvider(),
    ])
    catalog = builder.build(ctx)

    measured_diags = apply_measured(
        catalog, os.path.join(args.data_dir,
                              "capture/measurements/capture_results.json"))
    catalog.diagnostics.extend(measured_diags)

    if args.visual_pass:
        catalog.diagnostics.extend(apply_visual(catalog, args.visual_pass))

    out = args.out or os.path.join(args.data_dir, "catalog.json")
    catalog.save(out)
    s = catalog.stats
    print(f"catalog -> {out}")
    print(f"  total={s.total} kinds={s.by_kind} sources={s.by_source}")
    print(f"  measured={s.with_measured} visual={s.with_visual} "
          f"disagreements={s.disagreements} skipped={s.failed_sources}")
    if catalog.diagnostics:
        print(f"  diagnostics={len(catalog.diagnostics)} (first: {catalog.diagnostics[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
