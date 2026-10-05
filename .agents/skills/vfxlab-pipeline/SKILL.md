---
name: vfxlab-pipeline
description: Operate the vfxlab data and query pipeline in mcp-jev-recreated. Use when running vfx_find/vfx_inspect/vfx_preview (Jev ranking, passports, captured frames), executing probe captures (capture_plan, contact sheets, annotation passes), rebuilding data/catalog.json, running the Codex eval suite, or working with the jevlab-mcp stdio server and its eleven tools (6 scene lane + 5 fx-edit lane).
---

# vfxlab Pipeline

Commands, data artifacts, and measured facts for the two pipeline surfaces: **query side** (find → inspect → preview → eval) and **data side** (dumps → capture → sheets → visual passes → catalog rebuild). Everything below reflects real runs, not estimates.

## Bootstrap

This is one of 4 vfxlab skills. If you have not already loaded them this session, load the other three now — `vfxlab-use` (orchestration + safety rules), `vfxlab-scenes` (scene authoring/playback) and `vfxlab-fx-edit` (cloning/patching .fx resources) — then continue.

## Setup

```bash
pip install -e ".[dev]"        # needs setuptools>=64 for PEP 660 editable
pip install -e ".[mcp]"        # MCP server extra
export TYPESAFE_API_KEY=…      # live Jev calls (find/eval, -m typesafe tests)
```

Client-side work also needs Java 21 (`~/.jdks/temurin-21` or `$VFXLAB_JAVA_HOME`) + `xvfb-run`.

## Query side

| tool / command | what it does |
|---|---|
| `vfx_find(query, top_k)` / `jevlab find "<q>"` | live Jev ranking → top-k `{rank, id, source, kind, noul_relevance, choice_probability}` |
| `vfx_inspect(id)` | full passport — every layer (FAT view; not for ranking) |
| `vfx_preview(id)` | contact-sheet + per-angle frame paths + merged visual semantics |
| `vfx_fx_inspect` / `clone` / `patch` / `validate` / `register` | narrow Photon `.fx` customization lane — see `vfxlab-fx-edit` |
| `jevlab eval` | 12 Codex ability cases → recall@10, hit@1/3/10, MRR |

Jev semantics (verified): stage 1 = one `noul` independent-relevance question per candidate (batched, comparable); stage 2 = a single `choice` question over the stage-2 pool — probabilities are meaningful **only inside that one question**, never across batches. Jev is nondeterministic: ±1 expected id per run; judge changes over multiple runs, not one.

Measured operating point: `--batch-size 12 --stage2-pool 12` (current defaults). Counterintuitive but measured: **a deeper stage-2 pool lowers recall@10** (0.52 @ pool-25 vs 0.66 @ pool-12) — the sharper Choice distribution drops marginal expected ids entirely. Keep pool a parameter; don't widen defaults without a measured reason.

Query cache (`data/cache/find/`): keyed by normalized query + catalog `brief_hash` fingerprint + ranker params — re-enrichment or param changes auto-invalidate; `--no-query-cache` bypasses.

## Data side

```
probe dumps → tools/gen_capture_plan.py → runUitest capture
→ measurements + frames → tools/make_sheets.py → visual passes
→ tools/validate_pass.py → build_catalog (merge) → data/catalog.json
```

| step | command / artifact |
|---|---|
| plan | `python tools/gen_capture_plan.py` → `data/capture/capture_plan.json` (spawnable kinds only; composites → exceptions) |
| capture | `cd probe && xvfb-run -a ./gradlew runUitest --no-daemon` (selector via `-Pvfxlab.uitestSelection=`, e.g. `vfxlab.3_capture`; ~40 min for 197 shots) |
| outputs | `data/uitest-report/screenshots/…` + `data/capture/measurements/{capture_results,frames_index}.json` (rebuild index mid-run: `tools/rebuild_index.py`) |
| sheets | `python tools/make_sheets.py` → `data/capture/sheets/<shot>.png` (rows=angles, cols=ticks) |
| batches | `python tools/build_batches.py --batches N` → mixed-kind batch lists for annotation sub-agents |
| validate pass | `python tools/validate_pass.py <pass.json>` — structure: `{"observations": {shot: {visibility, description, properties{}, possible_roles[], confidence}}}`; visibility ∈ clear/faint/none/ambiguous |
| rebuild | `python -m jevlab.build_catalog --data-dir data --exceptions data/capture/exceptions.json --visual-pass <each batch file>` |

Visual-pass discipline: passes are **independent** — pass B agents never see pass A output; annotate only what frames show, never names/metadata; disagreement flags emerge on fully disjoint vocabulary at merge. `visual_status` on the passport (`observed` / `capture_failed:offscreen` / `environment_mismatch:requires_water`) gates what reaches the Jev brief — a failed capture is not a property of the effect.

## MCP server

`pip install -e ".[mcp]"` then `jevlab-mcp` (stdio). Six tools: `vfx_find`, `vfx_inspect`, `vfx_preview`, `vfx_scene_validate`, `vfx_scene_plan`, `vfx_scene_play`. Note: `mcp` 2.x renamed FastMCP → `mcp.server.mcpserver.MCPServer`.

## Measured numbers (current, committed)

- catalog: **4,432** passports; **207** answerable candidates (205 captured + 2 fx-edit clones); 0 build diagnostics
- capture: 197/197 spawnable shots, 3 angles × 3 ticks; visual passes A+B → 205/205 coverage (8 composite exceptions documented in `data/capture/exceptions.json`)
- best eval config (gated SELECTION BRIEF, 12/12): **recall@10 0.66, hit@1 0.67, hit@3 0.83, hit@10 0.92, MRR 0.750**; ~1.3 s/query, ~130k input tokens
- tests: 90 offline (`pytest tests/unit`), 2 live (`pytest -m typesafe`)
- known limits: `raiden_musou_isshin` 0/7 = expected-set granularity (composite-scene query vs accent-particle ids — not a top-10 size artifact); quasar eye-level render gap; ~34 passports carry `capture_failed`/`environment_mismatch` statuses by design

Committed vs regenerable: `data/catalog.json`, dumps, measurements, sheets manifest, evals are committed; `data/capture/frames/`, `data/captures/`, `data/cache/`, `probe/{build,run,.gradle}` are gitignored and regenerable.
