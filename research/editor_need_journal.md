# Photon-editor need — empirical journal

Real runs only. Each entry: what I wanted, what type of problem it was
(scene grammar vs resource/.fx), what I did, evidence (frame paths).

## Test 1 — directional laser (charge → beam → impact → decay)

Palette chosen from real sheets: cyan family
(`vfxlab:sparkle_sphere` orb, `vfxlab:laser_beam`, `superheroes:unibeam_spark`,
`superheroes:sword_explosion` residue, `minecraft:ash`).

### Run v1 — charge orb engulfed camera (scene-grammar fault)
- `sparkle_sphere` anchored `player.head` offset [0,-0.3,1.2] `follow:player`
  → its particle cloud fills the entire frame; nothing else visible.
- CLASS: scene grammar. Big persistent fx must be staged on `scene`/`ref`
  anchors a few blocks from the lens, not glued to the camera.

### Run v2 — beam fires along the view axis, reads as a blob (scene-grammar fault)
- `laser_beam` anchored `player.head` `to: ref:mark` `follow:player`:
  from the shooter's own camera the beam is nearly head-on → only its far
  end cluster shows; threequarter catches it at frame top edge, still no
  beam line.
- CLASS: scene grammar. A directional beam must originate at a scene anchor
  and travel across the frame. `to:` re-aims the fx ROOT rotation; verified
  the aim works (beam aimed at mark), the reading is just bad head-on.

### Want-to-edit-.fx log (Test 1)
1. **beam length/thickness fixed** — `laser_beam.fx` is `beam_emitter`,
   `width`+`duration`+`emitRate` are baked `constant` numbers; `to:` only
   rotates the root. Wanted: longer/thicker beam → needs .fx patch.
2. **beam color fixed** — baked `color`/texture `circle.png` ADDITIVE.
   Wanted (e.g.) red beam → needs .fx patch.
3. **fx options surface is empty** — spawn_specs maps every fx to
   `options: {}`; scene grammar can place/aim/track an fx but cannot tint,
   resize, or retime it. This is THE structural finding so far.
4. `minecraft:flash` passport = `capture_failed:offscreen` → dropped it;
   can't trust its framing. (catalog honesty check worked as designed.)
5. `homelander_laser_impact` sheet = empty at eye level → skipped.

### Run v3 — WORKS (with real resource-limit entries)
- Beam anchored `scene` pos [0,0,1.8] `to:` mark [0,-0.4,-4]:
  - `front t10` shows a clear diagonal cyan beam streak into the target
    cluster; `side_right t10/t18` shows it as a flat cyan ellipse/disc at
    the far end — the beam_emitter's baked length/tilt includes an upward
    bias so it overshoots the mark slightly rather than landing on it.
  - charge t6: sparkle_sphere + unibeam pulses read as a proper charge orb.
  - decay t36: sword_explosion embers + ash specks settling — subtle, good.
- VERDICT: charge → fire → impact → decay sequence ACHIEVED from catalog.
  Remaining wants (logged, unfixed):
  - beam `end`/length and up-tilt are baked constants in the .fx
    (`beam_emitter` config; scene `to:` only rotates the root) → can't land
    beam exactly on a target point or extend length. **.fx patch needed**
    if "beam that precisely tracks a target" matters.
  - beam `width` baked — can't thicken/thin via grammar. Same class.
  - palette lock stands (all cyan because I picked cyan resources — wanted,
    but any recolor = .fx patch).

## Test 2 — radial burst (buildup → burst → residual) — v1 SOLVED, no .fx want
- Pick from real sheets: `gust_emitter_large` (white wind rings),
  `sonic_boom` (teal burst core), `dust` buildup (tintable cyan),
  `enchant` glyphs, `unibeam_spark` residual accents, `white_smoke`, `ash`.
- `front t7`: white ring swooshes + smoke curls + big teal core =
  textbook radial shockwave. Buildup t4 gather readable; residual
  sparks/ash t10-t18 subtle but present.
- .fx wants: NONE. (white_smoke inherent faintness is a resource property,
  not an editable field — count/delta already settable.)
- rejected-on-evidence: `homelander_clap_dust` (sparse, dies by t8),
  `shriek` (thin ring spawns high, invisible at eye level).

## Test 3 — persistent aura around player

### Run v1 — mechanically tracks, optically unusable (scene-grammar + probe reality)
- `entity_effect` cyan at `player.chest` repeat every 4 + `enchant` feet +
  `blue_flame` feet + `end_rod` chest; tp at t20 to test tracking.
- t6: potion-swirl ring lands at camera feet — visible as a ground spiral.
- t14: frame EMPTY — one-shot particles at the lens drift below FOV;
  aura pulses leave visible gaps.
- t22/t32: aura re-anchored after tp → giant flat blue squares fill the
  frame (particles at near plane). It DID track the player — but tracking
  to the lens is useless.
- CLASS: mostly scene grammar (placement), but also an inherent probe
  constraint: player = camera, so "aura around the player" needs to sit at
  the body shell, not the eye.

### Run v2 — compose: wide ground ring + look-offset core (queued)
- entity_effect feet delta 1.3 (far rim visible at bottom) + enchant feet +
  blue_flame/end_rod at player.head look-offset [0,-0.5,2.0] follow-look →
  aura "face" floating ahead of camera, tracking the player.

### Want-to-edit-.fx log (Test 3, so far)
- none yet — but note: aura gaps at t14 are one-shot lifetime, a
  particle-level property (lifetime fixed per resource); mitigation =
  tighter repeat interval, i.e. scene grammar.

## Test 4 — fast melee / energy strike

### Rejected on measured evidence (resource-level gaps)
- `minecraft:sweep_attack` — sheet EMPTY at eye level (passport itself:
  "effect not visible in..."). THE vanilla melee arc can't be seen.
- `vfxlab:ribbon_trail` (trail_emitter fx) — sheet EMPTY at eye level too.
  A swing trail is exactly what a melee test wants; it renders nothing.
  **.fx-level limit** (can't enable/retune emitters from scene grammar).
- `minecraft:crit`, `enchanted_hit`, `damage_indicator` — all empty at
  eye level. The entire "hit feedback" vocabulary is invisible here.
- `superheroes:cap_shield_trail`, `kamehameha_trail` — visible but
  projectile-trail shaped (squiggle blob), not a strike.

### Run v1 — arc staged below the frame (scene-grammar fault)
- Sweep arc at pos ±1.5, y+0.2, z+2.0 → 45° off-axis + below centerline:
  outside FOV. t4 empty; t6-t9 only upward-drifting nightfall/gust caught
  at frame edges; t16 embers settling visible on the ground.
- CLASS: scene grammar (geometry math), not resources.

### Run v2 — raised arc into FOV (queued)
- arc ±1.0, y 0.6-0.9, z 1.8-1.9; gust swooshes t5-7 L→R + nightfall
  teal sweep accents + laser_beam as blade-flash diagonal +
  sword_explosion/unibeam impact at arc end + ash residual.

### Run v3 — staged INTO the frame, gust_emitter_large floods it
- mid-arc gust_emitter_large 1.9 blocks from camera → t5 huge white
  expanding ring + smoke, t6 whole upper frame = white/gray cloud,
  threequarter t6 = giant G-shaped curl filling a third of frame.
  t8 EMPTY — fast effects already dead, embers below FOV.
- CLASS: scene grammar (too close / wrong resource scale), not .fx —
  distance discipline fixed it.

### Run v4 — pulled strike zone to ~2.6 blocks, ring still over-large
- t5 big white ring partially in frame; t6 giant spiral, teal nightfall
  specks at edges; threequarter t6 readable sweep-curls across frame.
  Reads as "big wind shockwave", NOT a shaped strike.

### Run v5 — ribbon_trail + pos-track sweep: THE key negative result
- ribbon_trail fx anchored scene [0.9,0.8,1.0], track.pos sweeping
  −1.8x over 5 ticks (a painted arc!). Result: t7 front nearly EMPTY,
  threequarter t7 COMPLETELY EMPTY. The trail_emitter painted nothing —
  consistent with its catalog capture (empty at eye level); trail
  likely follows its transform in Local sim space so root motion
  doesn't paint a world-space ribbon.
- nightfall teal specks visible at top edges; t14 teal sparkles + cyan
  impact blocks + black ember specks drifting down = residual works.
- CLASS: **resource problem** — trail needs .fx patch (simulation space
  or vertex emission), or the trail is simply invisible at eye level.
  Not fixable from scene grammar.

### Verdict Test 4: NOT SOLVED from catalog+grammar.
Choreography produced a "fighty burst" (swoosh curls + teal accents +
impact embers + ash) but nothing reads as a shaped intentional strike.
Gaps: no visible slash-arc resource at eye level (sweep_attack, crit,
enchanted_hit, ribbon_trail ALL capture-empty); gust_* family is the
only "swoosh" and it reads as shockwave, not blade.
