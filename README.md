# mcp-jev-recreated — VFX Knowledge Base + Jev selector

Working (non-mock) pipeline that lets an LLM describe a desired visual effect
in plain text and get back the best **real, existing** Minecraft VFX resources
for it — ranked by Jev (TypeSafe AI) against a catalog built from actual mod
and vanilla resources.

## What it does

```
"translucent rings rippling out of the mouth in a cone"
        │
        ▼
VFX Knowledge Base (4,430 passports, real resources)
        │  particles · world events · photon fx/models/shaders/textures
        │  quasar emitters/particle defs/vfx params · composites
        ▼
passports: identity + factual + measured + visual semantics
        │  (measured = real in-game capture; visual = independent
        │   annotation passes, gated by visual_status reliability)
        ▼
Jev stage 1 — Noul independent relevance per candidate (batched)
Jev stage 2 — single Choice over the top pool
        │
        ▼
top-10: {rank, id, source, kind, noul_relevance, choice_probability, summary}
```

Measured end-to-end: **~1.3 s per query**, ~130k input tokens/query on the
4.4k-resource catalog (candidate-filtered to ~200 answerable entries,
full measured enrichment + reliability-gated visual semantics).

## Layout

| path | contents |
|---|---|
| `src/jevlab/providers/` | one provider per resource family |
| `src/jevlab/passports/` | passport schema + SemanticValue + content hash |
| `src/jevlab/catalog/` | catalog build/merge/stats |
| `src/jevlab/enrichment/` | measured + visual layer merging |
| `src/jevlab/jev/` | TypeSafe client (real API), question builders |
| `src/jevlab/ranking/` | two-stage selector |
| `src/jevlab/find_effects.py` | end-to-end query → top-K with query cache |
| `src/jevlab/evals/` | Codex ability eval harness |
| `src/jevlab/scene/` | scene spec → validation → probe playback plan → real-client run |
| `src/jevlab/mcp_server.py` | stdio MCP server: find/inspect/preview/scene tools |
| `probe/` | Fabric probe mod — registry dump + capture harness + scene playback (ldlib2 uitest) |
| `data/` | committed artifacts: dumps, measurements, contact sheets, catalog, evals |
| `docs/` | architecture, evaluation, research inventories |

## Usage

```bash
pip install -e .            # python >=3.10, deps: httpx, pytest
export TYPESAFE_API_KEY=…   # live TypeSafe/Jev key

# rebuild the catalog from committed dumps + all visual passes
python -m jevlab.build_catalog --data-dir data \
    --exceptions data/capture/exceptions.json \
    $(for f in data/visual/batches/batch_*.json data/visual/batches_b/group_*.json; do \
      printf -- "--visual-pass %s " "$f"; done)

# ask for an effect — real Jev calls, top-10 JSON
python -m jevlab.find_effects "a cold blue beam that holds for a second" \
    --top-k 10 --no-query-cache

# run the Codex ability eval (12 real ability descriptions)
python -m jevlab.evals.run_eval --out data/evals/results_gated_1212.json \
    --no-query-cache

# MCP server (pip install -e ".[mcp]")
jevlab-mcp   # stdio: vfx_find / vfx_inspect / vfx_preview /
             #          vfx_scene_validate / vfx_scene_plan / vfx_scene_play
```

### Scene playback

A scene spec stages several catalog resources on one tick timeline; the
probe replays it exactly in the real client and returns frames + per-angle
particle measurements.

```json
{"name": "demo", "duration": 30, "frames": [3, 8, 20],
 "camera": {"angles": ["front", "top"]},
 "steps": [
   {"tick": 2, "id": "minecraft:world_event/PARTICLES_DESTROY_BLOCK", "pos": [0,-0.5,0]},
   {"tick": 3, "id": "minecraft:sonic_boom"},
   {"tick": 5, "id": "superheroes:homelander_roar_dust", "pos": [0,0,-1]},
   {"tick": 10, "id": "minecraft:dust", "options": {"color": [0.2,0.6,1.0], "scale": 2}}
 ]}
```

`vfx_scene_play` (or `jevlab.scene.play.play_scene`) compiles it against the
catalog — unknown ids, non-spawnable kinds and missing required parameters
are hard errors; `requires_water` / `offscreen` capture history becomes
warnings — writes `data/capture/scene/scene_plan.json`, runs
`runUitest -Pvfxlab.uitestSelection=vfxlab.4_scene` under xvfb (needs Java
21 at `~/.jdks/temurin-21` or `$VFXLAB_JAVA_HOME`), and returns the frame
paths + spawned counts per angle.

## Tests

```bash
pytest tests/unit          # 52 tests, offline, seconds
pytest tests/ -m typesafe  # 2 live API tests, needs TYPESAFE_API_KEY
```

## Current numbers (all real, see docs/evaluation.md)

- catalog **4,430** resources: 142 particle types, 82 world events, 5 photon
  .fx, 6 meshes, 130 photon shaders/postfx, 3,910 textures, 15 quasar emitters,
  132 quasar particle defs, 8 composites — **0 build diagnostics**
- measured layer: **197 captured shots** (3 angles × 3 ticks, real
  Minecraft; every shot spawned server-side particles)
- visual layer: **197/197 shots annotated** — pass A on all, independent
  pass B on the 78 ambiguous/low-confidence shots; 73 disagreement flags
- visual coverage of answerable candidates: **205/205** (197 annotated +
  8 documented unrenderable composite exceptions); visual reliability:
  166 observed / 27 capture_failed / 4 environment_mismatch
- Codex eval with SELECTION BRIEF + visual gate (best measured config,
  batch/pool 12/12): **recall@10 = 0.66**, hit@1 = 0.67, hit@3 = 0.83,
  hit@10 = 0.92, MRR = 0.750, ~1.3 s/query, ~130k input tokens/query.
  Full attribution matrix (gating recovered the −0.18 visual regression
  and doubled hit@1) in docs/evaluation.md.
- scene lane (verified live): demo scene `roar_burst` — 5 steps across 4
  resource kinds replayed twice (front+top), 137/157 spawned particles,
  6 frames captured, ~41 s wall-clock end-to-end
- 54 tests green (52 offline + 2 live)

See `docs/architecture.md` for design, `docs/evaluation.md` for full eval
results and known limits.
