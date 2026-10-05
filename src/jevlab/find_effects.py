"""find_effects — the pipeline entry point.

    python -m jevlab.find_effects "a roar that pushes air forward"
        [--catalog data/catalog.json] [--top-k 10] [--stage2-pool 25]
        [--batch-size 30] [--no-query-cache] [--out result.json]

Loads the built catalog, filters to answerable candidates (spawnable
effects — texture/mesh/shader materials are catalogued but never offered as
answers), runs the two-stage Jev ranking against the real TypeSafe API, and
writes the ranked result. Query results are cached under the catalog's
content fingerprint; --no-query-cache forces a live pass.
"""
from __future__ import annotations

import argparse
import json
import os

from .cache.layered import LayeredCache, catalog_fingerprint
from .catalog.builder import Catalog
from .jev.client import TypeSafeClient
from .ranking.selector import RANKER_VERSION, EffectSelector

#: kinds that can directly answer an effect request
ANSWERABLE_KINDS = frozenset({
    "particle", "parameterized_particle", "world_event",
    "fx", "quasar_emitter", "composite",
})


def answerable(catalog: Catalog) -> list:
    out = []
    for p in catalog.resources.values():
        if not p.ready_to_use or p.kind not in ANSWERABLE_KINDS:
            continue
        if p.kind == "world_event" and not p.factual.get("has_visual"):
            continue
        out.append(p)
    return out


def find(query: str, catalog_path: str, *, top_k: int = 10,
         stage2_pool: int = 12, batch_size: int = 12,
         use_query_cache: bool = True, cache_root: str = "data/cache",
         deadline_s: float | None = None) -> tuple[dict, dict]:
    """Returns (result_dict, meta). Cached hits return the stored dict with
    a 'served from query cache' diagnostic appended."""
    catalog = Catalog.load(catalog_path)
    candidates = answerable(catalog)
    fp = catalog_fingerprint({p.id: p.brief_hash() for p in candidates})
    cache = LayeredCache(cache_root)
    qkey = cache.query_key(query, fp, RANKER_VERSION, {
        "top_k": top_k, "stage2_pool": stage2_pool,
        "batch_size": batch_size})

    meta = {"catalog": catalog_path, "candidates": len(candidates),
            "catalog_fingerprint": fp, "query_cache": "live"}
    if use_query_cache:
        hit = cache.get("query", qkey)
        if hit is not None:
            meta["query_cache"] = "hit"
            r = dict(hit["result"])
            r["diagnostics"] = list(r.get("diagnostics", [])) + [
                "served from query cache"]
            return r, meta

    with TypeSafeClient() as client:
        selector = EffectSelector(
            client, batch_size=batch_size,
            stage2_pool=stage2_pool, top_k=top_k, deadline_s=deadline_s)
        result = selector.find_effects(query, candidates)
    if use_query_cache:
        cache.put("query", qkey, {"result": result.to_dict()})
    return result.to_dict(), meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--catalog", default="data/catalog.json")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--stage2-pool", type=int, default=12)
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--no-query-cache", action="store_true")
    ap.add_argument("--deadline", type=float, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    result, meta = find(
        args.query, args.catalog, top_k=args.top_k,
        stage2_pool=args.stage2_pool, batch_size=args.batch_size,
        use_query_cache=not args.no_query_cache, deadline_s=args.deadline)
    payload = {"meta": meta, **result}
    out = json.dumps(payload, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
