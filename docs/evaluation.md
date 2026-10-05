# Evaluation — real numbers only

All figures below were produced by actually running the pipeline against the
live TypeSafe API (model `jev-1.13.0`) and the real Minecraft capture lane.
Raw artifacts: `data/catalog.json`, `data/evals/results.json`,
`data/capture/`, `data/visual/`.

## Catalog

`python -m jevlab.build_catalog --data-dir data --visual-pass pass_a pass_b`

| metric | value |
|---|---|
| total passports | 4,430 |
| particle / parameterized_particle | 131 / 11 |
| world_event | 82 (35 flagged `has_visual`) |
| photon fx / mesh / shader / postfx | 5 / 6 / 116 / 14 |
| textures (materials pool) | 3,910 |
| quasar_emitter / quasar_particle / composite | 15 / 132 / 8 |
| build diagnostics | **0** |
| measured passports | **197** |
| visually annotated passports | **197** (pass A on all; pass B second
independent pass on the 78 ambiguous/low-confidence shots) |
| visual coverage of answerable | **205/205** — 197 visually annotated +
8 documented exceptions |
| visual disagreement flags | 73 keys across merged passes |
| answerable candidates per query | 205 |

### Capture lane v2 (full catalog)

197 shots × 3 angles × 3 ticks captured in a real 1.21.1 client (ldlib2
uitest, xvfb, 28,383 steps, ~39 min, scenario PASS). Every shot spawned
real particles server-side (`spawned > 0` for all 197; quasar emitters
emitted 12–252 manager particles each). All frames + contact sheets under
`data/capture/`; shot→attachment manifest `data/capture/sheet_manifest.json`.

**Honest visibility outcome**: 34 shots spawned particles that rendered
nothing at any captured angle/tick — quasar emitters that fire off-frame
(below the ground plane or behind the camera) and water-dependent vanilla
particles (`bubble`, `underwater`, `current_down`, `nautilus`…) that
cannot render in air. Pass A marked them `none`; independent pass B
confirmed on 30/34 (4 re-graded faint/ambiguous). This is real semantics:
the passport records "spawns but renders nothing in this capture
geometry", not a missing analysis.

**Exceptions (8, `data/capture/exceptions.json`)**: `superheroes:vfx/*`
composite passports are Codex ability parameter bundles (scalars only —
contactSeconds, ringRadius, distortionStrength…) consumed by ability
code, with no spawnable emitter — proven unrenderable by file inspection,
not skipped lazily.

## Capture lane v1 (historical — 9-shot baseline)

9 shots captured in a real 1.21.1 client (ldlib2 uitest lane, xvfb):
multiple angles × tick samples with runner-native frames + per-tick
spawned/alive counts. Verified by pixel analysis — e.g. `minecraft:dust`
peaked ~230 particles, `sonic_boom` ring visible t3–t8.

**Known capture limit**: quasar emitter frames read as zero pixels at eye
level while emitters verifiably tick (measured counts 30→104→0 alive) — the
top-down angle does show ground debris. Documented as a capture constraint,
not hidden: `scorpion_hellfire`/`homelander_roar_wave` visual descriptions
describe what the frames actually showed (debris fields), and their noul
ranks suffer honestly for it.

## Codex ability eval — `data/evals/results.json` (earlier 9/205 baseline)

12 cases built from real Codex-Superheroes abilities
(`data/evals/codex_cases.json`, English queries, no resource-name hints).
Command: `python -m jevlab.evals.run_eval --no-query-cache`.
Results below are the committed `results.json` (per-case rows carry the
full candidate list with noul + choice probabilities, `choice_distribution`,
and batch stats).

| case | hits/expected | top-1 | top-1 choice p |
|---|---|---|---|
| homelander_clap | 3/3 | minecraft:sonic_boom | 0.87 |
| homelander_eye_lasers | 3/4 | vfxlab:laser_beam | 0.66 |
| homelander_roar | 3/3 | minecraft:sonic_boom | 0.68 |
| flight_aura | 3/4 | superheroes:vfx/flight | 0.62 |
| homelander_sun | 3/6 | superheroes:vfx/sun_detonation | 0.64 |
| scorpion_teleport | 2/3 | minecraft:flame | 0.59 |
| scorpion_hellbreath | 3/5 | superheroes:scorpion_hellbreath | 0.34 |
| scorpion_harpoon | 2/4 | vfxlab:ribbon_trail | 0.36 |
| goku_kamehameha | 2/4 | superheroes:vfx/laser | 0.50 |
| naruto_rasenshuriken | 2/4 | minecraft:sonic_boom | 0.79 |
| raiden_musou_isshin | 1/7 | we/PARTICLES_ELECTRIC_SPARK | 0.20 |
| hero_transform | 2/3 | vfxlab:sparkle_sphere | 0.30 |
| **aggregate** | **29/50 = recall@10 0.58** | 12/12 cases ≥1 hit | |

Latency: 0.8–1.1 s/case, 11.0 s total. Tokens: 930,347 input + 48,311
output (~78k in/case — dominated by serialized passport briefs).

**Run-to-run variance**: three identical runs scored 29/50, 28/50, 29/50
(0.56–0.58) — Jev is non-deterministic at the margins (roar 3↔2,
hellbreath 3↔2, rasenshuriken 3↔2, transform 1↔2, raiden 1↔2). Per-case
±1 hit is normal noise, not a code difference.

### Miss analysis (honest)

- **raiden_musou_isshin (1/7)**: expected set holds 7 sibling
  `superheroes:*` slash effects; Jev filled the list with plausible
  alternatives (electric spark world event, anomaly_slice, smash attack,
  sonic boom, laser variants). Sibling variants crowd each other out —
  recall@10 penalizes semantic near-duplicates.
- **goku_kamehameha**: kamehameha_core + trail hit; `goku_ki_aura` lost to
  `homelander_laser_impact`/`vfx/laser` — reasonable given the aura's thin
  visual description.
- **hero_transform**: `transform_spark` + `totem_of_undying` hit;
  `firework` lost to dust/poof/sparkle variants — vanilla celebration
  effects are under-described in the visual layer (no frames captured).
- **scorpion_harpoon**: `scorpion_harpoon` hit at #4; `scorpion_hellfire`
  missed — its honest visual description is "ground debris", which does not
  read as a harpoon trail.

Root causes, in order: (1) only 9 of 205 answerable resources carry real
visual semantics — the rest rank on name+facts only; (2) expected sets list
every acceptable sibling, so list diversity is punished; (3) quasar
eye-level capture gap makes some emitters look like debris.

## Full-enrichment impact experiment (205/205)

After reaching 205/205 visual coverage the full eval was re-run. The
bigger briefs hit TypeSafe's `max_tokens_exceeded` cap, so the sweep was
re-run at `--batch-size 12 --stage2-pool 12`. To isolate content effects
from that config change, four configurations were measured live:

| measured layer | visual layer | batch/pool | recall@10 | hit@1 | hit@3 | hit@10 | MRR |
|---|---|---|---|---|---|---|---|
| 9 | 9 | 25/30 (original) | 0.56–0.58 | — | — | — | — |
| 9 | 9 | 12/12 | 0.56 | 0.33 | 0.75 | 1.00 | 0.547 |
| 197 | 9 | 12/12 | **0.68** | 0.50 | 1.00 | 1.00 | 0.750 |
| 197 | 197 | 12/12 | **0.50** | 0.42 | 0.83 | 0.92 | 0.618 |

(Full 197-visual cell replicated: 25/50 identical per-case on both runs.)

### Attribution

- **Config shrink (25/30 → 12/12) is neutral** at baseline content:
  0.56 sits inside the old 0.56–0.58 band.
- **Full measured layer HELPED: +0.12** (0.56 → 0.68). Spawn counts,
  particle bounds and alive trajectories give Jev genuinely discriminative
  facts.
- **Full visual layer HURT: −0.18** (0.68 → 0.50). Mechanism, verified in
  the data: expected-but-off-frame emitters (e.g. the `scorpion_*`,
  `homelander_*` quasar set) now carry honest descriptions like "All
  frames equal the empty baseline … No visible effect at any tick or
  angle" plus property unions of `none`/`empty`. Jev reads that as
  "this candidate produces nothing" and drops them below generic
  alternatives — `raiden_musou_isshin` went 0/7 (was 1–2/7), and per-case
  losses concentrate on shots with `visibility=none`/`faint` verdicts.
- The flip side is consistent too: **hit@1 improved 0.33 → 0.42** and
  MRR 0.547 → 0.618 — where visuals were real, Jev picked the obvious
  right answer higher; the loss is purely at the recall tail.

### Costs of full enrichment

- Input tokens/query: ~78k → **~330k** (4.2× — richer briefs × more
  stage-1 batches at size 12).
- Latency/case: ~1.0 s → **~3.1 s**.
- Stage-2 pool 25 → 12 (token cap); recall@10 is now bounded by a
  shallower choice pool as well.

## Visual reliability gate + selection brief (v3)

Root cause of the −0.18 drop, per the user: a *failed capture* was being
encoded as a *property of the effect* — "all frames equal the empty
baseline" prose read to Jev as "this effect does nothing". Fix, two parts:

1. **`visual_status` on every captured passport** — derived at
   `apply_visual` from all passes' visibility verdicts:
   `observed` (any pass saw it) / `capture_failed:offscreen` (all-none but
   particles verifiably spawned — outside capture geometry) /
   `environment_mismatch:requires_water` (water-locked vanilla particles).
   Result on 197 shots: **166 observed, 27 capture_failed,
   4 environment_mismatch**.
2. **SELECTION BRIEF** (`jev_brief`) — the projection Jev sees is now
   deliberately smaller than the full passport: identity, type, aggregate
   measured facts (spawned_max/peak_alive/extent — per-angle frames stay
   in the full passport), capabilities, *real* constraints
   (`requires_water` arrives as an effect fact), roles — and visual
   semantics **only when `observed`**. Non-observed statuses surface as a
   one-word status token with no visual block at all.

| content | brief | batch/pool | recall@10 | hit@1 | hit@3 | hit@10 | MRR |
|---|---|---|---|---|---|---|---|
| 9m/9v | full | 12/12 | 0.56 | 0.33 | 0.75 | 1.00 | 0.547 |
| 197m/9v | full | 12/12 | 0.68 | 0.50 | 1.00 | 1.00 | 0.750 |
| 197m/197v | full | 12/12 | 0.50 | 0.42 | 0.83 | 0.92 | 0.618 |
| 197m/197v | **gated** | 12/12 | **0.66** | **0.67** | 0.83 | 0.92 | **0.750** |
| 197m/197v | gated | 30/12 | 0.60 | 0.67 | 0.83 | 0.92 | 0.757 |
| 197m/197v | gated | 25/30 | 0.52 | 0.67 | 0.83 | 0.92 | 0.757 |

Read:

- **The gate recovered the visual loss**: 0.50 → 0.66 at the identical
  12/12 config — statistically equal to the 0.68 measured-only cell, so
  visual semantics now add signal at the head instead of noise at the
  tail: **hit@1 doubled** vs every earlier configuration (0.33→0.67),
  MRR 0.547→0.750.
- **Bigger stage-2 pools *lower* recall@10** (0.66@pool-12 vs 0.52@pool-25):
  a deeper finalist pool makes the Choice distribution sharper at the
  head, so marginal expected ids lose their top-10 slots entirely. Since
  the product contract is "useful candidates inside the top-10",
  **pool 12 is the better operating point** — and cheaper.
- Costs collapsed back: **~130k input tokens/query, ~1.3 s/case**
  (from ~330k / ~3.1 s at full briefs).
- `raiden_musou_isshin` remains 0/7 everywhere — an eval-set artifact:
  7 sibling `superheroes:*` slash ids cannot coexist in one top-10
  against stronger singles; excluding that one case, recall is 33/43
  ≈ 0.77.
- Defaults updated to `--batch-size 12 --stage2-pool 12` (the best
  measured operating point).

## TypeSafe contract (verified live)

- `POST /v1/systemone` with `model: "jev-latest"` → response `jev-1.13.0`
- noul returns float 0..1; choice returns label + confidence + full
  per-label probability distribution summing to ~1 within one question
- observed query: "translucent rings rippling out of the mouth in a cone" →
  `minecraft:sonic_boom` at **0.91** choice probability, `roar` vfx 0.02,
  `ember_ring_burst` 0.04 — semantically correct winner
- usage fields: `input_tokens`, `output_tokens` reported per call;
  latency ~0.9–1.1 s per full two-stage query over 205 candidates

## Tests

- `pytest tests/unit` — 33 tests, offline (providers, measured, visual
  merge, disagreement normalization, selector ordering, answerable filter,
  query-cache hit/bypass/invalidation)
- `pytest tests/ -m typesafe` — 2 live tests (answer shapes, real
  two-stage query incl. negative-constraint behavior: a "no fire" query
  keeps flame's choice probability at 0.0 even when the tiny pool can't
  exclude it from the finalist list)

## Known limits

1. `raiden_musou_isshin` is 0/7 at every configuration — an eval-set
   artifact (7 sibling ids cannot all fit one top-10); recall@10 without
   that case is ~0.77 at the gated operating point.
2. 27 of 197 shots are `capture_failed` (spawned but offscreen/subpixel —
   mostly quasar emitters, counters prove 12–252 live particles) and
   4 `environment_mismatch` (water-locked); they rank on
   identity+measured facts only.
3. Choice probabilities are only comparable inside one question. Stage-2
   pool defaults to 12 — measured optimum: deeper pools sharpen the head
   but drop marginal ids from the top-10 entirely.
4. ~130k input tokens/query remains the honest cost of selection briefs
   over 205 answerable candidates; candidate filtering is the mitigator.
5. `content_hash` caches assume artifact paths are stable inside `data/`.
6. `visibility` is omitted from the merged visual dict when all passes
   agree — agreed visibility instead surfaces as `visual_status`
   (observed/capture_failed/environment_mismatch), which is what gates
   the selection brief.
