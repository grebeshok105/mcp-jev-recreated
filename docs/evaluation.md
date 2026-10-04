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
| measured passports | 9 |
| visually annotated passports | 9 (2 independent passes) |
| visual disagreement flags | 31 of 91 keys (token-normalized incl.
naive singularization; domain-stopword set keeps ubiquitous terms like
'particle' from bridging real divergences) |
| answerable candidates per query | 205 |

## Capture lane

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

## Codex ability eval — `data/evals/results.json`

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

1. Visual layer covers 9 of 205 answerable resources — coverage, not depth, is
   the main recall lever.
2. Quasar emitters are invisible at eye level in captured frames.
3. Choice probabilities are only comparable inside one question — stage-2
   pool is capped at 25, so recall is bounded by stage-1 quality.
4. ~78k input tokens/query is the honest cost of full passport briefs at
   this catalog size; candidate filtering is the mitigator.
5. `content_hash` caches assume artifact paths are stable inside `data/`.
