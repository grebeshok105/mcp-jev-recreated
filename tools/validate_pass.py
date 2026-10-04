#!/usr/bin/env python3
"""Validate a visual-pass JSON produced by a sub-agent.

Checks structure matches what enrichment/visual.merge_passes consumes:
{"observations": {shot_key: {visibility, description, properties{prop:[str]},
possible_roles[], confidence: number}}}

Usage: python tools/validate_pass.py <pass.json> [--expect shot1,shot2,...]
Exit 0 = valid; prints per-shot problems otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys

VALID_VISIBILITY = {"clear", "faint", "none", "ambiguous"}


def validate(path: str, expect: list[str] | None) -> int:
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: unreadable json: {exc}")
        return 1
    obs = doc.get("observations")
    if not isinstance(obs, dict) or not obs:
        print("FAIL: no 'observations' dict")
        return 1
    problems = []
    covered = set()
    for shot, o in obs.items():
        covered.add(shot)
        if not isinstance(o, dict):
            problems.append(f"{shot}: observation not a dict")
            continue
        vis = o.get("visibility")
        if vis not in VALID_VISIBILITY:
            problems.append(f"{shot}: visibility={vis!r} not in {sorted(VALID_VISIBILITY)}")
        desc = o.get("description")
        if not isinstance(desc, str) or len(desc) < 20:
            problems.append(f"{shot}: description missing or too short")
        props = o.get("properties")
        if not isinstance(props, dict) or len(props) < 4:
            problems.append(f"{shot}: properties missing/sparse ({type(props)})")
        else:
            for pk, pv in props.items():
                if not isinstance(pv, list) or not all(isinstance(v, str) for v in pv):
                    problems.append(f"{shot}: property {pk} not a list of strings")
        conf = o.get("confidence")
        try:
            c = float(conf)
            if not 0 <= c <= 1:
                problems.append(f"{shot}: confidence {c} out of range")
        except (TypeError, ValueError):
            problems.append(f"{shot}: confidence {conf!r} not numeric")
        roles = o.get("possible_roles", [])
        if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
            problems.append(f"{shot}: possible_roles not a list of strings")
    if expect:
        missing = [s for s in expect if s not in covered]
        extra = [s for s in covered if s not in expect]
        if missing:
            problems.append(f"missing shots: {missing}")
        if extra:
            problems.append(f"unexpected shots: {extra}")
    if problems:
        print(f"FAIL ({len(problems)} problems, {len(covered)} shots covered):")
        for p in problems[:40]:
            print(" -", p)
        return 1
    print(f"OK: {len(covered)} shots covered, structure valid")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--expect", default=None, help="comma-separated shot keys")
    args = ap.parse_args()
    expect = args.expect.split(",") if args.expect else None
    return validate(args.path, expect)


if __name__ == "__main__":
    sys.exit(main())
