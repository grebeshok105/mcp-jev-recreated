# Architecture

## Layers

```
providers → passports → catalog → measured → visual → selector → top-K
```

### 1. Providers (`src/jevlab/providers/`)

Each provider emits `Passport` objects for one resource family. A provider
reads raw dumps produced by the probe mod inside a real Minecraft dev client
(`probe/` → `data/capture/dump/*.json`), never guesses names from memory.

| provider | count | kinds |
|---|---|---|
| `particles.py` | 142 | `particle` (131) + `parameterized_particle` (11) — full codec schemas for dust, vibration, block, item, entity_effect, etc. |
| `world_events.py` | 82 | `world_event` — capability flags (sound/particles/animation/block-state) |
| `photon.py` | 3,757 | `fx` (5), `mesh` (6), `shader` (116), `postfx_graph` (14), `texture` (3,616) |
| `quasar.py` | 449 | `quasar_emitter` (15), `quasar_particle` (132), `composite` (8), `texture` (294) |

Provider isolation: any single broken dump/artifact degrades only its own
source (`stats.failed_sources`), never the build. Asset ids carry a directory
prefix (`particle_def/`, `vfx/`, `tex/`) so a Quasar `ash.json` cannot collide
with the `minecraft:ash` ParticleType.

### 2. Passports (`src/jevlab/passports/schema.py`)

Layers: `identity`, `factual` (schema-declared truth: codec fields, spawnable,
capability tags), `measured` (capture-derived stats), `visual` (merged
`SemanticValue`s: values + confidence + disagreement + evidence),
`possible_roles`, `diagnostics`, `provenance`.

Invariants:
- `unknown` = absent key, never `false`. `answerable()` and Jev briefs treat
  missing data as unknown.
- `content_hash()` covers the static layers (identity+factual) and drives
  the pipeline caches; `brief_hash()` covers everything `jev_brief` emits
  (all layers the model sees) and drives the query-cache fingerprint, so
  re-enrichment invalidates cached rankings.
- `jev_brief()` projects a compact, field-ordered dict for the model;
  `one_line()` renders the human summary.

### 3. Measured enrichment (`enrichment/measured.py`)

Probe capture writes `data/capture/measurements/capture_results.json`
(per-shot, per-angle, per-tick: spawned/alive counts, bounds, frames).
`shot_resource_id` maps shot names to catalog ids (`levelevent_2001` →
`minecraft:world_event/PARTICLES_DESTROY_BLOCK`, first-underscore namespaced).
`summarize_angles` produces `spawned_max`, `peak_alive`,
`first_visible_tick`, `extent_blocks`, `angles_covered`, `frames_captured`.

### 4. Visual enrichment (`enrichment/visual.py`)

Two annotation passes run as **independent** sub-agent sessions over the same
contact sheets (each saw only the images; B never saw A's output). Merge
rules:

- union of observed values per property key, each tagged with evidence
  (`a`/`b`);
- `disagreement` flags only when the two passes use **fully disjoint content
  tokens** — a shared content token suppresses the flag. `_tokens()` strips
  timing qualifiers (`t3`, `t8`), stopwords, punctuation and naive
  singularization (`puffs`→`puff`) so trivial phrasing doesn't fake
  divergence — genuinely different vocabulary still flags. Result: 29
  flagged keys / 91 — real divergences like bright-vs-matte and
  clear-vs-faint.

### 5. Jev client (`src/jevlab/jev/`)

`TypeSafeClient` → `POST https://api.typesafe.ai/v1/systemone`,
`Authorization: Bearer`. Questions: `noul` (0..1 float), `choice`
(label + confidence + full probability distribution), `score` (weighted).
Resilience: bounded retries with exponential backoff, honors `Retry-After`
on 429, per-call deadline, typed errors (`JevAuthError`, `JevRateLimitError`,
`JevNetworkError`, `JevResponseError`), usage/latency accounting.

### 6. Two-stage selector (`ranking/selector.py`)

Stage 1 — candidates are split into batches (default 30); **one Noul question
per candidate**, so scores are comparable across batches.
Stage 2 — **one Choice call** over the top-`stage2_pool` finalists (default
25). Choice probabilities are meaningful only inside a single question; they
are never compared across batches — the finalist pool is a single question.
Final order = stage-2 probability desc, then id; top-K (default 10) returned.

### 7. `find_effects` + caches

`answerable()` filters the catalog: `ready_to_use` kinds only —
`particle`, `parameterized_particle`, `world_event` (must have
`has_visual`), `fx`, `quasar_emitter`, `composite`. Materials/textures/
shaders stay in the KB but never reach Jev. 4,430 → 205 candidates.

Query cache: `data/cache/find/` keyed by normalized query + catalog
fingerprint (digest of answerable passports' `brief_hash()` — measured and
visual changes invalidate) + ranker params (`top_k`, `stage2_pool`,
`batch_size`). `--no-query-cache` bypasses read+write. A changed catalog or
changed rank params misses the cache automatically.

## Probe mod (`probe/`)

Fabric mod inside the LDLib2 dev environment. `runUitest` (xvfb) runs
`group:vfxlab`:

- `RegistryDump` → `particle_types.json`, `particle_providers.json`,
  `world_events`, photon asset listings, quasar module scans.
- `CaptureRun` executes `capture_plan.json` shots: spawn via
  `Spawner`/`ParticleOptionsFactory`, tick, capture frames at multiple angles
  and ticks via the runner's own `b.screenshot()` (the only capture that
  includes the particle pass), measure live counts through the
  `ParticleEngine` mixin + quasar manager introspection.

## Failure design

- one broken resource/dump → degraded source, build continues, diagnostic
  recorded;
- Noul answers missing/invalid for a batch member → `noul_relevance = None`,
  diagnostic, other candidates unaffected;
- Choice failure → fall back to Noul ordering;
- all Jev calls bounded by `--deadline`; diagnostics propagate to the result
  JSON.
