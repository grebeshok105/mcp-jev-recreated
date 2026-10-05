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
- `jev_brief()` projects the SELECTION BRIEF — a compact projection for
  the model (identity, type, aggregate measured facts, capabilities, real
  constraints, roles, and visual semantics only when `visual_status ==
  "observed"`); `one_line()` renders the human summary. `visual_status`
  (`observed` / `capture_failed:offscreen` / `environment_mismatch:
  requires_water`) is derived from all passes' visibility verdicts at
  `apply_visual` time: a capture that saw nothing is a property of the
  capture, not of the effect, so non-observed statuses never reach Jev as
  visual semantics.

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
  (`a`/`b`); malformed records (non-dict observations, non-list values,
  non-numeric confidence) are skipped, never fatal;
- `disagreement` flags only when the two passes use **fully disjoint content
  tokens** — a shared content token suppresses the flag. `_tokens()` strips
  timing qualifiers (`t3`, `t8`), connective/domain stopwords (ubiquitous
  terms like `particle`/`speck` can't bridge real divergence), punctuation
  and naive singularization (`puffs`→`puff`) so trivial phrasing doesn't
  fake divergence — genuinely different vocabulary still flags. Result:
  31 flagged keys / 91 — real divergences like bright-vs-matte and
  clear-vs-faint.

### 5. Jev client (`src/jevlab/jev/`)

`TypeSafeClient` → `POST https://api.typesafe.ai/v1/systemone`,
`Authorization: Bearer`. Questions: `noul` (0..1 float), `choice`
(label + confidence + full probability distribution), `score` (weighted).
Resilience: bounded retries with exponential backoff, honors `Retry-After`
on 429, per-call deadline, typed errors (`JevAuthError`, `JevRateLimitError`,
`JevNetworkError`, `JevResponseError`), usage/latency accounting.

### 6. Two-stage selector (`ranking/selector.py`)

Stage 1 — candidates are split into batches (default 12); **one Noul question
per candidate**, so scores are comparable across batches.
Stage 2 — **one Choice call** over the top-`stage2_pool` finalists (default
12). Choice probabilities are meaningful only inside a single question; they
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

### 8. Scene lane (`src/jevlab/scene/`)

Stages several catalog resources on one tick timeline and replays them
inside the real client. One spec drives preview and gameplay identically —
the probe is the only runtime; validation states honestly what the runtime
cannot do (e.g. `follow` on instantaneous kinds, `rotation/scale` tracks on
quasar emitters).

**Grammar v2** (see `examples/follow_beam.scene.json`):

- *Anchors* — `anchor`: `scene`, `player` (feet, `.chest`, `.head`, `.look`),
  `camera`, `ref:<step name>`; `offset [x,y,z]` in the direction's local
  frame; `distance` pushes along the direction.
- *Directions* — `world` | `player.look` | `[yaw,pitch]` |
  `{"face": <anchor expr>}`; `to: <anchor expr>` faces a target point.
- *Follow* — `follow: "player"` re-resolves the anchor every tick on
  persistent handles (`fx`, `quasar_emitter`).
- *Tracks* — `track.pos` keyframes `[t,x,y,z]` (fx + quasar), `rotation` /
  `scale` (fx only); ticks are relative to the step's spawn.
- *Repeat* — `{every, count}` | `{every, until}` on a step or a whole
  `groups[]` block; expansion happens at compile time.
- *Refs* — a named step (`name:`) is addressable as `ref:<name>` in anchor
  positions and option values (e.g. `destination: "ref:zap"`); producers
  must sort before their consumers.
- *Commands* — `commands:[{tick, command}]` fire server commands mid-scene
  (e.g. move the player to prove follow).

- `spec.py` — validates all of the above against the catalog (unknown ids,
  non-spawnable kinds, unresolvable params, bad refs/ordering = errors;
  `environment_mismatch` / `capture_failed` passports and follow-on-instant
  = warnings). Same-tick refs are legal when the producer sorts first.
- `compile.py` — normalized spec → `scene_plan.json` (repeat/group
  expansion to absolute ticks; shot specs from `spawn_specs.shot_spec_for`,
  user options merged over tuned defaults).
- `play.py` — writes `data/capture/scene/scene_plan.json`, launches
  `runUitest -Pvfxlab.uitestSelection=vfxlab.4_scene` (xvfb, Java 21), and
  reads back `scene_results.json` + the frame index.

Note: in the probe the local player *is* the camera — player-anchored
effects land at the viewpoint, so visible staging usually wants a look
offset (`offset: [0, -0.5, 2.0]` = ahead of the camera) or scene-anchored
positions.

### 9. MCP server (`src/jevlab/mcp_server.py`, optional `mcp` dep)

stdio MCPServer exposing the lane boundaries as tools:

| tool | wraps |
|---|---|
| `vfx_find` | `find_effects.find` — live Jev top-k |
| `vfx_inspect` | full passport from `data/catalog.json` |
| `vfx_preview` | contact-sheet URL + per-angle frames + visual semantics |
| `vfx_scene_validate` | `validate_scene` |
| `vfx_scene_plan` | `compile_scene` |
| `vfx_scene_play` | `play_scene` — real playback → frames + measurements |

## Probe mod (`probe/`)

Fabric mod inside the LDLib2 dev environment. `runUitest` (xvfb) runs
`group:vfxlab` (override with `-Pvfxlab.uitestSelection=<selector>`):

- `RegistryDump` → `particle_types.json`, `particle_providers.json`,
  `world_events`, photon asset listings, quasar module scans.
- `CaptureRun` executes `capture_plan.json` shots: spawn via
  `Spawner`/`ParticleOptionsFactory`, tick, capture frames at multiple angles
  and ticks via the runner's own `b.screenshot()` (the only capture that
  includes the particle pass), measure live counts through the
  `ParticleEngine` mixin + quasar manager introspection.
- `SceneRun` (`vfxlab.4_scene`) replays `scene_plan.json`: one camera
  teleport per angle, then the tick timeline — each step resolves its
  anchor expression (`AnchorResolver`: scene/player/camera/ref anchors,
  rotated local offsets, look/face directions), `ref:` option values are
  substituted with named steps' resolved positions, follow + track
  keyframes are driven per tick on live handles (quasar
  `ParticleEmitter.setPosition`, fx `root.updatePos/updateRotation/
  updateScale`), tick-scheduled `commands` run on the server, frames
  screenshot at the requested ticks, `stop_after` handles torn down per
  angle. Deterministic (fixed tick schedule), so every angle sees the
  identical timeline. Writes `scene_results.json` +
  `scene_frames_index.json`.

## Failure design

- one broken resource/dump → degraded source, build continues, diagnostic
  recorded;
- Noul answers missing/invalid for a batch member → `noul_relevance = None`,
  diagnostic, other candidates unaffected;
- Choice failure → fall back to Noul ordering;
- all Jev calls bounded by `--deadline`; diagnostics propagate to the result
  JSON.
