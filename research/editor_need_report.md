# Photon editor need — empirical report

Date: 2026-10-05. Evidence: 4 full find→inspect→preview→scene→validate→play→iterate
cycles on the live VFXLab (real-client playback, frames reviewed by eye).
Journal: `research/editor_need_journal.md`. Frame sets: `research/frames/` (v*-prefixed).
Scene specs: `scenes/laser_sequence`, `scenes/radial_burst`, `scenes/following_aura`,
`scenes/melee_strike`. No `.fx` touched, no editor API written.

## Per-test verdicts

| Test | Result | Iterations | Main gap |
|---|---|---|---|
| 1. Directional laser (charge→beam→impact→decay) | **SOLVED** | 3 | beam geometry baked (see below) |
| 2. Radial burst / shockwave | **SOLVED** | 1 | none |
| 3. Persistent aura following player | **SOLVED** (with caveats) | 3 | probe optics, palette lock |
| 4. Fast melee / energy strike | **NOT SOLVED** | 5 | no visible slash-arc resource |

**3 of 4 solved entirely from catalog + scene grammar.** The unsolved one is a
catalog gap (the "shaped strike" vocabulary renders nothing at eye level), not an
orchestration failure — see below.

## Every "want to edit .fx" moment actually logged

Frequency matters: these are all the moments across ~12 playback runs and
30+ inspected frames.

1. **Beam geometry baked** (Test 1): `vfxlab:laser_beam` is a `beam_emitter`;
   length/width/emitRate/color are baked `constant` numbers. `to:` only rotates
   the fx root — the beam overshoots its mark slightly and always up-tilts.
   Wanted: override length, straighten axis. → genuinely needs a `.fx` channel.
2. **`fx` / `quasar_emitter` spawn options surface is `{}`** — there is literally
   no param channel to any fx resource. Even a trivial tint is impossible today.
   That is the single most striking absence.
3. **Palette locks** (Tests 1,3): sparkle_sphere is cyan, blue_flame is blue,
   sword_explosion embers are orange-white. Wanted "red aura core" or
   recolorable orb → needs a different resource or a color patch. (Dust and
   entity_effect ARE tintable via `options.color` — parameterized particles
   already carry that channel; fx does not.)
4. **ribbon_trail paints nothing** (Test 4): trail_emitter + `track.pos`
   sweep produced no visible ribbon in any frame — consistent with its empty
   catalog capture. Probably Local simulation space (root motion carries the
   whole trail) or an eye-level render gap. Either way: fixable only inside
   the `.fx`, not from grammar.
5. **Whole hit-feedback vocabulary invisible at eye level** (Test 4):
   sweep_attack, crit, enchanted_hit, damage_indicator, electric_spark,
   homelander_laser_impact — all captured EMPTY. That's a mass `.fx`-level
   problem: the catalog has the right *names* for melee but none draw.
   (Whether each is fixable by patching vs being truly invisible needs a
   per-resource look — flagged honestly.)
6. **Scale/distance can't be pushed through `options`** (Tests 2,4):
   gust_emitter_large is dramatic at 3.5 blocks and frame-flooding at 2 —
   wanted a "half-scale gust" for close range. No scale param on particle
   resources; only fx accepts `track.scale`.
7. **One-shot particle lifetime is fixed per resource** (Test 3): aura
   flicker between repeat pulses — solved in grammar (tighter `repeat.every`),
   but a "longer-lived mote" wish is a lifetime patch.
8. **Internal animation / direction** (Test 1): gust curls always rise
   ~1.5 blocks and die in ~3 ticks; beam up-tilts. Direction of baked motion
   is not steerable — rotation track only turns the root facing.

Total: **8 distinct wants across 4 tests** — none edited, all journal'd.

## Scene-grammar vs resource problems (the honest split)

Scene-grammar problems (fixed by re-staging, NOT by an editor):
- v1 melee arc below the FOV; aura particles at the lens; framing across
  camera angles; repeat-interval gaps; `ref:` ordering; count/first-tick
  semantics. All solved by editing the **spec**, not the resource.
- Strike choreography *mechanics* work fine: per-tick timing, offsets,
  cross-step refs, tracks, commands, tp-forced re-anchoring — playback
  reported 0 errors in every run.

Resource problems (only a `.fx` channel could touch):
- items 1,2,3,4,5,6,7,8 above — all baked constants inside resources.

## Answers to the original questions

**Is a Photon editor needed?** Yes — but a narrow one. 3/4 ability archetypes
build today; the blockers are concentrated, not diffuse. The bottleneck is
NOT "design effects in a graph" — it is a missing **parameter channel** and a
**small set of value patches**.

**How often did it actually come up?** Every test hit at least one .fx want;
the laser wanted geometry on run 1. But only Test 4 was actually *blocked*
(catalog-wide slash gap). Frequency: real but concentrated.

**Which tasks solved without it?** Laser sequence, radial burst, following
aura — all reach "reads correctly on captured frames" quality today.

**Where exactly did VFXLab hit walls?** (a) fx options surface is empty;
(b) no scale/duration channel on particle resources; (c) baked beam
geometry; (d) invisible-at-eye-level melee vocabulary; (e) palette locks
on colored resources.

**Which .fx ops turned out actually necessary?** Ranked by real frequency:
1. **Scalar patch** — duration, emitRate, size/width, speed, lifetime
   (items 1,6,7). One op covers the largest share of wants.
2. **Color/tint patch** (items 2,3) — aura recolor, orb recolor.
3. **Clone-resource** — so patches land on `mymod:laser_beam_long`,
   not the shared resource (implicit requirement of all patches).
4. **Layer/emitter toggle** — "remove the smoke layer from X" came up
   implicitly with gust_emitter_large's smoke flood (item 6); this is
   per-emitter disable, already visible in the NBT (emitters are separate
   compound nodes).
5. **Visibility/space fix for trail+hit particles** (items 4,5) — a
   simulation-space or offset patch; narrower, possibly per-resource
   quirks rather than one general op.
6. **Direction/curve retune** (item 8) — wanted, rare.

**Minimal API that covers most cases:** `inspect_fx` (decode NBT → tree of
emitters/params/values — the strings-table already proves this is readable),
`clone_fx`, `patch_fx` (set scalar / color / toggle emitter by path),
`validate_fx` (schema + spawn in capture harness), `register_fx` (catalog
passport so find/inspect/scene see the clone). That's 5 ops — no graph model.

**What NOT to automate:** graph layout/node editing; multi-emitter
choreography INSIDE an fx (scene grammar already does inter-resource
timing — don't duplicate it); texture/material authoring; arbitrary curve
editing; anything requiring visual judgment a capture can't verify.
Also don't automate *authoring* new emitters — every solved test reused
stock resources; the grammar's job is composition.

**Graph editor or inspect/clone/patch/validate?** Narrow
**inspect/clone/patch/validate** — decisively. The evidence shows discrete
constant-value wants, not topology wants: nobody needed to rewire emitters,
add nodes, or change blending. A graph API is a solution without a
matched problem in these runs.

## Bonus finding

`track.pos` on fx is verified working as a channel (playback applied it,
no errors) — so "scripted motion" exists; what lacks is *visible* material
to move (trail, arcs). Also the catalog's `visual_status` honesty
(capture_failed flags) correctly predicted every empty-at-eye-level
resource — the enrichment pipeline earns its keep.

## Bottom line

An editor is needed, but the right shape is a **param-patch lane**
(inspect → clone → patch → validate → register), not a graph editor.
Largest single win: expose the `{}` fx options surface to
duration/emitRate/scale/color + emitter toggles.
