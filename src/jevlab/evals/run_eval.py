"""Codex ability evaluation — real queries against the live pipeline.

    python -m jevlab.evals.run_eval [--cases data/evals/codex_cases.json]
        [--catalog data/catalog.json] [--no-query-cache] [--limit N]
        [--out data/evals/results.json]

Each case sends its natural-language query through find_effects and scores
whether ground-truth resource ids appear in the returned top-K. Reports
hit@top10 per case plus aggregate recall; stores every candidate list so
reviewers can audit the ranking, not just the score.
"""
from __future__ import annotations

import argparse
import json
import os
import time

from ..find_effects import find


def run_cases(cases_path: str, catalog_path: str, *, top_k: int = 10,
              stage2_pool: int = 12, batch_size: int = 12,
              use_query_cache: bool = True, limit: int | None = None,
              deadline_s: float | None = None) -> dict:
    cases = json.load(open(cases_path))
    if limit:
        cases = cases[:limit]
    report = {"cases": [], "started_at": time.time(),
              "top_k": top_k, "stage2_pool": stage2_pool,
              "batch_size": batch_size}
    hits = evaluated = 0
    for case in cases:
        result, meta = find(
            case["query"], catalog_path, top_k=top_k,
            stage2_pool=stage2_pool, batch_size=batch_size,
            use_query_cache=use_query_cache, deadline_s=deadline_s)
        ranked_ids = [c["id"] for c in result["candidates"]]
        expected = case["expected_ids"]
        got = [e for e in expected if e in ranked_ids]
        hits += len(got)
        evaluated += len(expected)
        first_rank = next(
            (i + 1 for i, rid in enumerate(ranked_ids) if rid in expected),
            None)
        report["cases"].append({
            "name": case["name"], "query": case["query"],
            "expected_ids": expected,
            "top_ids": ranked_ids,
            "hits": got,
            "missed": [e for e in expected if e not in ranked_ids],
            "hit_at_topk": len(got) / max(len(expected), 1),
            "first_hit_rank": first_rank,
            "hit_at_1": first_rank == 1,
            "hit_at_3": first_rank is not None and first_rank <= 3,
            "hit_at_10": first_rank is not None and first_rank <= 10,
            "reciprocal_rank": (1.0 / first_rank) if first_rank else 0.0,
            "candidates": result["candidates"],
            "choice_distribution": result.get("choice_distribution"),
            "stats": result["stats"],
            "usage": result["stats"]["usage"],
            "latency_s": result["stats"]["latency_s"],
            "query_cache": meta["query_cache"],
            "diagnostics": result.get("diagnostics", []),
        })
        print(f"[{case['name']}] hits {len(got)}/{len(expected)} "
              f"({100*len(got)/max(len(expected),1):.0f}%) "
              f"latency={result['stats']['latency_s']:.1f}s "
              f"tok={result['stats']['usage']}")
    report["finished_at"] = time.time()
    report["aggregate"] = {
        "cases": len(report["cases"]),
        "expected_total": evaluated,
        "hits_total": hits,
        "recall_at_topk": hits / max(evaluated, 1),
        "cases_with_any_hit": sum(1 for c in report["cases"] if c["hits"]),
        "hit_at_1": sum(1 for c in report["cases"] if c["hit_at_1"])
                    / max(len(report["cases"]), 1),
        "hit_at_3": sum(1 for c in report["cases"] if c["hit_at_3"])
                    / max(len(report["cases"]), 1),
        "hit_at_10": sum(1 for c in report["cases"] if c["hit_at_10"])
                     / max(len(report["cases"]), 1),
        "mrr": round(sum(c["reciprocal_rank"] for c in report["cases"])
                     / max(len(report["cases"]), 1), 4),
        "total_input_tokens": sum(c["usage"]["input_tokens"]
                                  for c in report["cases"]),
        "total_output_tokens": sum(c["usage"]["output_tokens"]
                                   for c in report["cases"]),
        "total_latency_s": round(sum(c["latency_s"]
                                     for c in report["cases"]), 2),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="data/evals/codex_cases.json")
    ap.add_argument("--catalog", default="data/catalog.json")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--stage2-pool", type=int, default=12)
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-query-cache", action="store_true")
    ap.add_argument("--deadline", type=float, default=None)
    ap.add_argument("--out", default="data/evals/results.json")
    args = ap.parse_args()

    report = run_cases(
        args.cases, args.catalog, top_k=args.top_k,
        stage2_pool=args.stage2_pool, batch_size=args.batch_size,
        use_query_cache=not args.no_query_cache, limit=args.limit,
        deadline_s=args.deadline)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    a = report["aggregate"]
    print(f"\naggregate: {a['hits_total']}/{a['expected_total']} "
          f"recall@top{report['top_k']}={a['recall_at_topk']:.2f} "
          f"hit@1={a['hit_at_1']:.2f} hit@3={a['hit_at_3']:.2f} "
          f"hit@10={a['hit_at_10']:.2f} mrr={a['mrr']:.3f} "
          f"({a['cases_with_any_hit']}/{a['cases']} cases with a hit) "
          f"tokens={a['total_input_tokens']}+{a['total_output_tokens']} "
          f"latency={a['total_latency_s']}s -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
