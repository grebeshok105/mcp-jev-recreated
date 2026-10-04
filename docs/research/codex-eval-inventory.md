# Codex-Superheroes — VFX evaluation inventory

Repo: `grebeshok105/Codex-Superheroes` @ `main` (HEAD `be526ea3`). Source analysis only — nothing was run or modified. All paths are repo-relative.

## 0. Architecture cheat-sheet (how any ability's VFX actually fires)

- Server side calls `VfxFx.event(source, effectId, origin, target, scale)` / `VfxFx.eventAround(level, …)` / `VfxFx.channel(player, channelId, START|UPDATE|STOP, target)` — `src/main/java/io/github/grebeshok105/codex/core/net/VfxFx.java`. These send typed S2C payloads (`VfxEventS2CPayload`, `VfxChannelS2CPayload`) via `FxBroadcast` (`src/main/java/io/github/grebeshok105/codex/core/net/FxBroadcast.java`).
- Client side, `VfxRuntime` (`src/client/java/io/github/grebeshok105/codex/client/core/vfx/VfxRuntime.java`) resolves the effect/channel id to a registered `VfxEffectFactory` / `VfxChannelFactory` (registered per-hero via `HeroClientContext.vfx(...)` / `.vfxChannel(...)`), culls spawns >160 blocks from the camera, caps at 256 live effects, and ticks/renders them on `AFTER_TRANSLUCENT`.
- Tunables are data-driven: `VfxParamsLoader` (`src/client/java/io/github/grebeshok105/codex/client/core/vfx/params/VfxParamsLoader.java`) loads every `assets/superheroes/vfx/<path>.json` into `VfxParams` keyed `superheroes:<path>` — live-reloaded on F3+T.
- Render-side, an effect composes primitives from `client/core/vfx/pattern/` — `ShockwavePattern` (expanding ring), `BeamPattern`/`BeamLook` (styled cross-beam via `CrossBeamRenderer`), `TrailPattern` (camera-facing ribbon), `ImpactPattern` (surface emitter burst + distortion kick), `ScreenFlash`, `CameraImpulse` (screen shake), `AuraPattern`, `PhaseTimeline` — and backend calls on `VfxBackends.current()` (`client/core/vfx/backend/`).
- `VfxBackend` = the Veil seam: `emit(quasar emitter id, pos)`, `light(pos, rgb, radius, brightness)`, `flash(intensity, rgb)`, `distortion(center, radius, strength)`. `VeilVfxBackend` implements them with Quasar emitters, `PointLightData` dynamic lights and the `vfx_*` post pipelines (`client/core/vfx/veil/VeilVfxBackend.java`, `VeilPostEffects.java`); `FallbackVfxBackend` no-ops emit/light/distortion and degrades flash to a HUD overlay (`client/core/vfx/backend/FallbackVfxBackend.java`).
- Server-owned legacy visuals still exist alongside: direct `level.sendParticles(...)` (vanilla + modded `SimpleParticleType`s) and `level.playSound(...)`.

---

## 1. Evaluation ability set (12 visually distinct abilities)

### 1.1 Homelander — Hand Clap (radial air-impact burst)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/hero/homelander/ability/HandClapAbility.java` — sends `VfxFx.event` for `homelander/clap` (activate, l.81), `homelander/clap_cancel` (l.128), `homelander/clap_impact` (hit frame ~1.5 s in, l.151). Also fired by the boss mob: `content/boss/homelander/entity/ai/HomelanderHandClapGoal.java`.
- **What fires today** (`src/client/java/.../client/hero/homelander/fx/ClapFx.java`, params `assets/superheroes/vfx/homelander/clap.json`): `homelander.hand_clap` sound at construction; at contact — a Veil point-light flash between the hands (fades over 8 ticks), `ImpactPattern` burst of quasar emitter `homelander_clap_flash` + a `distortion` kick, one `homelander_clap_dust` emitter at the ground, an expanding `ShockwavePattern` ring (radius 5, 10 ticks, pale cyan), a dust cone marched along the eye→forward axis (10 steps × 1.5 blocks, one `homelander_clap_dust` per step), and a proximity-scaled `CameraImpulse` shake (radius 24, 16 ticks). On a Veil-free client only the ring, shake and sound survive.
- **Candidate eval query:** "a very short, powerful air impact burst from a hand clap — a hard flash at the hands, a fast expanding shock ring in front of the player, dust kicked up along the direction, violent but readable, done in under a second"
- **Ground truth (should rank high):** quasar burst emitters (`homelander_clap_flash`, `homelander_clap_dust`), `ShockwavePattern`, `ImpactPattern`, `VfxBackend.light`, `VfxBackend.distortion`, `CameraImpulse`, `homelander.hand_clap` sound, `vfx/homelander/clap.json` params.
- **Edge constraints:** "must not look like fire or smoke — this is compressed air, no flame colors"; "the whole effect must be under ~1 s, no lingering trail or glow".

### 1.2 Homelander — Eye Lasers (sustained twin beams)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/hero/homelander/ability/EyeLasersAbility.java` — `VfxFx.channel(player, homelander/laser, START|UPDATE|STOP, end)` (l.111/120/129); server also records block-face scorch marks via `LaserScorchSync` (l.222–224, `hero/homelander/scorch/`).
- **What fires today** (`src/client/java/.../fx/EyeLaserChannel.java`, params `vfx/homelander/laser.json`): a channel effect — two `BeamPattern` cross-beams anchored at `HumanoidAnchors.eyes` converging on one point (local caster: per-frame raycast + entity chest snap; remote: server-sent end lerped over the 2-tick UPDATE cadence). `PhaseTimeline` gives a 6-tick charge ramp, hold, 8-tick release fade; `homelander.laser.loop` entity-bound hum ramps/fades to match. Every 3 ticks: `ImpactPattern` burst of `homelander_laser_impact` at the end point plus a tracking point light. Madness state widens the beams ×2.4. Scorched blocks render `textures/effect/homelander/laser_scorch.png` decals via `ScorchMarkRenderer`/`ScorchMarkStore`.
- **Candidate eval query:** "twin bright energy beams streaming continuously from the eyes that converge on whatever is being looked at, hot core with a softer colored glow around it, charred marks left on blocks the beam touches, hums while held and snaps off cleanly"
- **Ground truth:** `BeamPattern`/`BeamLook`/`CrossBeamRenderer`, `VfxChannelEffect` + `VfxChannelS2CPayload`, `HumanoidAnchors.eyes`, `PhaseTimeline`, quasar `homelander_laser_impact`, `VfxBackend.light`, `ScorchMarkRenderer` decal + `ScorchMarksS2CPayload`, `homelander.laser.*` sounds, `vfx/homelander/laser.json`.
- **Edge constraints:** "must persist indefinitely while held — not a projectile"; "beam origin must track the character's eyes in any pose, including flight tilt".

### 1.3 Homelander — Stunning Roar (sonic shockwave cone)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/hero/homelander/ability/StunningRoarAbility.java` — `VfxFx.event(ROAR, mouth, mouth + forward·RADIUS)` (l.74).
- **What fires today** (`src/client/java/.../fx/RoarFx.java`, params `vfx/homelander/roar.json`): two layered contract sounds (`homelander.roar` + `homelander.roar.deep`), then ~1.5 s of mouth-anchored sonic-wave cone: a `ShockwavePattern` ring + `homelander_roar_wave` quasar emitter every 3 ticks marching along the look axis (spacing 1.5, radius 2.2), a `distortion` pulse every 10 ticks, `homelander_roar_dust` at the feet every 5 ticks, and a low proximity-scaled `CameraImpulse` rumble. The mouth anchor re-reads the source entity every tick so the cone follows the head.
- **Candidate eval query:** "a roar that visibly pushes air forward — repeated translucent rings rippling out of the mouth in a cone, faint heat-haze shimmer, dust stirring on the ground, lasting about a second and a half"
- **Ground truth:** `ShockwavePattern` (repeated rings), quasar `homelander_roar_wave` + `homelander_roar_dust`, `VfxBackend.distortion`, `CameraImpulse`, layered `homelander.roar*` sounds, `vfx/homelander/roar.json`.
- **Edge constraints:** "the wave must stay anchored to the caster's face while they turn or move"; "directional cone — not an omni explosion; nothing behind the caster".

### 1.4 Homelander — Supersonic flight (persistent contrail + boost ring)

- **Ability class:** shared `mechanic/flight` (`mechanic/ability/FlightAbility.java`); client driven by `client/core/flight/FlightPoseTracker` (spawns the registered `trailEffect`/`boostEffect`, l.161–164 & 234–237) and `ctx.flightPresentation` wired in `client/hero/homelander/fx/HomelanderFx.java` l.53–61.
- **What fires today** (`src/client/java/.../fx/FlightFx.java`, params `vfx/homelander/flight.json`, pose tuning `vfx/flight/pose.json`): TRAIL — four `TrailPattern` ribbons pushed per tick: a dense vapor core + wide translucent sheath off the chest and hairline speed streaks off both fists (texture `textures/effect/soft_trail.png`), plus a `ShockwavePattern` pressure ring every 12 ticks perpendicular to smoothed velocity once speed ≥ ringSpeed for 5 ticks; self-terminates below CRUISE. BOOST — `homelander_flight_boost` emitter burst + expanding ring on BOOST entry. LANDING (`homelander/landing`) — `homelander_flight_landing` impact burst + distortion + ring + shake + impact-scaled `homelander.flight.land`. Loop/takeoff/boost sounds come from `FlightPresentation`.
- **Candidate eval query:** "a supersonic flight aura — a soft white vapor contrail streaming off the torso and thin speed lines off the fists while flying fast, and a small shock ring popping periodically like breaking the air barrier"
- **Ground truth:** `TrailPattern` (ribbon/contrail), `ShockwavePattern`, `FlightPresentation`/`FlightPoseTracker`, `ClientFlightState` phases, quasar `homelander_flight_boost`/`homelander_flight_landing`, `ImpactPattern`, `textures/effect/soft_trail.png`, `vfx/homelander/flight.json` + `vfx/flight/pose.json`, `homelander.flight.*` sounds.
- **Edge constraints:** "effect must persist for the whole flight and stop immediately on landing or slowdown — not a one-shot"; "must follow a prone/flying pose, not assume an upright body".

### 1.5 Homelander — Sun charge → detonation (charge-up then massive blast)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/hero/homelander/runtime/HomelanderMadnessAftermathController.java` — `VfxFx.eventAround(SUN_CHARGE)` l.54, `SUN_DETONATION` l.78 (madness-crash reuses detonation scaled down, `HomelanderVfxIds.MADNESS_CRASH`).
- **What fires today:** `SunChargeFx` (`src/client/.../fx/SunChargeFx.java`, `vfx/homelander/sun_charge.json`) — ~200-tick aura bound to the nearest player: growing point light, rising `homelander_sun_ember` emitters, heat `distortion`, entity-bound `homelander.sun.charge` sound ramping volume+pitch, local camera tremble. `SunDetonationFx` (`src/client/.../fx/SunDetonationFx.java`, `vfx/homelander/sun_detonation.json`) — distance+LOS-attenuated `ScreenFlash`, huge fading core light (radius ~48, 60 ticks), two expanding `ShockwavePattern` rings (14 and 8), `distortion` pulse, `homelander_sun_ember` + `homelander_sun_debris` bursts (ember repeats ×3), proximity shake, `homelander.sun.detonate` sting.
- **Candidate eval query:** "a long visible charge-up where the character glows hotter and brighter, embers rising off them, then a huge screen-filling solar explosion with an expanding ring of fire and debris"
- **Ground truth:** `ScreenFlash`, `VfxBackend.light` (long-lived fading light), `ShockwavePattern`, quasar `homelander_sun_ember`/`homelander_sun_debris`, `VfxBackend.distortion`, `CameraImpulse`, `homelander.sun.*` sounds, `VfxFx.eventAround` (no-source world-fixed event), `vfx/homelander/sun_*.json`, `textures/vfx/homelander/sun_*.png`.
- **Edge constraints:** "the charge phase must read for several seconds before the blast — not an instant explosion"; "the flash must wash out the screen briefly but not blind permanently (attenuated by distance/line of sight)".

### 1.6 Scorpion — Fire Teleport (hellfire blink)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/hero/scorpion/ability/ScorpionFireTeleportAbility.java` — flame burst + `ScorpionFx.teleport` at origin (l.72–73) and again at destination (l.104–105); vanilla `FLAME` burst via `spawnFlameBurst` (l.129).
- **What fires today:** server sends `ScorpionFxS2CPayload KIND_TELEPORT` (`hero/scorpion/net/ScorpionFx.java`); on the client `ClientScorpionFx.play` → `VeilScorpionFx.teleport` (`src/client/.../scorpion/fx/veil/VeilScorpionFx.java`) spawns quasar emitter `scorpion_teleport` (light-emitting flame burst). Vanilla side: `FLAME` ×50 + `BLAZE_SHOOT` at departure, `FLAME` + `FIRECHARGE_USE` + `ENDERMAN_TELEPORT` at arrival. Teleport itself goes through `SafeTeleport.clamp`.
- **Candidate eval query:** "an instant blink teleport — the character erupts in a burst of hellish flame where they stood and reappears at the target inside a second matching flame burst"
- **Ground truth:** quasar `scorpion_teleport` (+ `scorpion_burst`/`scorpion_pillar` modules, `render/color/hellfire.json`), `ScorpionFxS2CPayload`, `ClientScorpionFx`/`VeilScorpionFx` dispatch, vanilla `FLAME`/`LAVA` particles, `SafeTeleport`, blaze/firecharge teleport sounds.
- **Edge constraints:** "fire is mandatory here — it is a hell-themed teleport, not a purple portal"; "must leave a burst at BOTH ends, and the arrival burst is the one players judge".

### 1.7 Scorpion — Hell Breath (sustained flame cone)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/hero/scorpion/ability/ScorpionHellBreathAbility.java`; the per-tick emission lives in `hero/scorpion/runtime/ScorpionController.java` l.203–220 — `ScorpionFx.breath` every 8 ticks.
- **What fires today:** `VeilScorpionFx.breath` spawns `scorpion_hellbreath` emitters at 1.5/3/4.5/6 blocks along the look direction; vanilla `FLAME` particles stream in a widening cone (spread grows with distance), `LAVA` + `LARGE_SMOKE` at ~70 % range every 4 ticks, `BLAZE_BURN` loop every 10 ticks. Damage AABB follows the cone.
- **Candidate eval query:** "a sustained stream of hellish fire pouring out of the mouth like a flamethrower — a widening cone of flames with embers and dark smoke at the far end, held for as long as the button is held"
- **Ground truth:** quasar `scorpion_hellbreath` + `scorpion_breath`/`scorpion_burst` modules, `hellfire` render color, `ClientScorpionFx`/`VeilScorpionFx`, vanilla `FLAME`/`LAVA`/`LARGE_SMOKE` cone math in `ScorpionController`, `BLAZE_BURN` loop.
- **Edge constraints:** "sustained channel — must emit continuously, not fire-and-forget"; "flame cone must widen with distance, not stay a thin beam".

### 1.8 Scorpion — Spear / harpoon ("GET OVER HERE" chain projectile)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/hero/scorpion/ability/ScorpionSpearAbility.java` — on hit: `ScorpionFx.harpoon(level, eye, center)` l.101, `ScorpionController.startSpearPull`, `scorpion.get_over_here` sound, `FLAME` trail along the line + `CRIT`/`LAVA`/`SWEEP_ATTACK` at the target.
- **What fires today:** `VeilScorpionFx.harpoon(from, to)` spawns `scorpion_harpoon` emitters at 6 lerp points along the throw line plus a `scorpion_hellfire` pillar flare where it skewers; vanilla `FLAME` dots the whole path; the target is ignited and pulled (`startSpearPull`).
- **Candidate eval query:** "a burning chain harpoon that streaks out, skewers the target in a flare of fire, and drags them back — a fiery dotted line from the thrower to the victim"
- **Ground truth:** quasar `scorpion_harpoon` + `scorpion_hellfire` (pillar) emitters, `scorpion_harpoon`/`scorpion_pillar` modules, `hellfire` render color, `ScorpionFxS2CPayload`, `ScorpionController.startSpearPull`, vanilla `FLAME`/`CRIT`/`LAVA` trail, `scorpion.get_over_here` sound.
- **Edge constraints:** "the trail is a straight chord caster→target, not a lobbed arc"; "impact flare only when the spear actually lands — no flare on a whiff".

### 1.9 Goku — Kamehameha (charged energy beam barrage)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/hero/goku/ability/GokuKamehamehaAbility.java` (+ `hero/goku/registry/GokuParticles.java`).
- **What fires today:** charge phase — `superheroes:goku_kamehameha_core` particles orbiting the hands in a growing sphere + `BEACON_AMBIENT` ticks; release — a thick beam built from batched `sendParticles`: `goku_kamehameha_core` + `goku_kamehameha_trail` + `END_ROD` packets with elongated spread boxes every ~1.5 blocks out to 30 blocks (`RANGE`), `EXPLOSION` bursts at the impact point, `WARDEN_SONIC_BOOM` + `BEACON_ACTIVATE`/`CONDUIT_ACTIVATE` sounds. Damage scales with consumed ki stacks.
- **Candidate eval query:** "a massive blue-white energy wave fired from cupped hands after a visible charge-up — a thick continuous beam of light that pours forward for seconds and explodes where it lands"
- **Ground truth:** `superheroes:goku_kamehameha_core`/`goku_kamehameha_trail`/`goku_ki_aura` particle types (EndRod provider, custom textures), `ChargeSession` charge→release phases, vanilla `END_ROD`/`EXPLOSION`, elongated-box `sendParticles` batching, sonic-boom/beacon sound stack.
- **Edge constraints:** "the beam is thick and volumetric — a wall of energy, not a laser line"; "charge phase must show the energy ball growing in the hands before release".

### 1.10 Naruto — Rasenshuriken (thrown spinning energy disc)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/hero/naruto/ability/NarutoRasenshurikenAbility.java` (+ `hero/naruto/registry/NarutoParticles.java`); `KageBunshinEntity` exists but the shuriken itself is a ChargeSession-tracked invisible projectile, not an entity.
- **What fires today:** charge — `naruto_rasengan_swirl` sphere + `GUST` around the hand (`BREEZE_CHARGE`); launch — `BREEZE_SHOOT`; flight — the invisible head streams `naruto_rasengan_swirl` (28/tick) + `SWEEP_ATTACK` each tick while travelling at fixed speed; hit — victims take rasenshuriken damage + WITHER + push, `GUST_EMITTER_LARGE` + `WIND_CHARGE_BURST`.
- **Candidate eval query:** "a spinning chakra disc hurled like a frisbee — a swirling white-blue vortex of wind that visibly screws through the air and bursts on whoever it clips"
- **Ground truth:** `superheroes:naruto_rasengan_swirl` particle type, `ChargeSession` projectile ticking, vanilla `GUST`/`SWEEP_ATTACK`/`GUST_EMITTER_LARGE`, breeze/wind-charge sound stack.
- **Edge constraints:** "must read as rotation/vortex, not a plain glowing ball"; "travels as a projectile — the swirl follows the moving head, not the caster's hand".

### 1.11 Raiden — Musou Isshin (charged sword strike + lightning storm)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/hero/raiden/ability/RaidenMusouIsshinAbility.java` → `hero/raiden/runtime/RaidenMusouIsshinController.java` (global tick, `RaidenModule` l.42).
- **What fires today:** windup (`WINDUP_TICKS` = 3 s charge with countdown, strike lane `SLASH_LENGTH` = 45 blocks) — `FLASH` + `moonveil` burst at the caster, pulsing `anomaly_slice` + `ELECTRIC_SPARK` along the strike lane, `jiwald_effect` orbiting, `BEACON_ACTIVATE`/`TRIDENT_THUNDER`/`AMETHYST_BLOCK_RESONATE` rising pitch; resolve — a carved terrain slash (`carveSlash` breaks blocks along the lane), 4 real `LightningBolt` visual-only entities planted along the strike line, heavy `anomaly_slice`/`moonveil`/`sparks`/`EXPLOSION` bursts per lane segment, `FLASH` + `white_boom` + `sword_explosion` ×90 + `shamak` at the end. Nearby enemies frozen during windup.
- **Candidate eval query:** "an overcharged katana ultimate — the fighter freezes the area while power gathers, then one enormous slash that rips up the ground and drops a row of lightning bolts along the cut"
- **Ground truth:** `LightningBolt` entities (`setVisualOnly`), `superheroes:anomaly_slice`/`moonveil`/`jiwald_effect`/`sparks`/`white_boom`/`sword_explosion`/`shamak`, `ChargeSession`-style windup queue, `WorldDestructionPolicy` terrain carve, thunder/sweep/amethyst sound stack.
- **Edge constraints:** "real lightning bolts must be part of it — particle sparkles alone are not the target look"; "windup telegraphs the strike for several seconds before it lands".

### 1.12 Hero transformation (identity-swap poof)

- **Ability class:** `src/main/java/io/github/grebeshok105/codex/core/transform/HeroTransformService.java` — `playTransformFx(player, activate)` l.122–135; same `TRANSFORM_SPARK` reused by `mechanic/flight/FlightController.java` l.223 (takeoff).
- **What fires today:** on transform — `superheroes:transform_spark` ×60 in a ~0.8-block cloud around the player + `BEACON_ACTIVATE`; on revert — vanilla `SMOKE` ×30 + a lower sound. The type is one of the original `ModParticles` (EndRod sprite, `textures/particle/transform_spark.png`, ungated in `CoreFx`).
- **Candidate eval query:** "a quick magical poof of sparkles wrapping the body for an instant as one character swaps into another — bright, celebratory, gone in a blink"
- **Ground truth:** `superheroes:transform_spark` particle type + `particles/transform_spark.json` + texture, `ModParticles`/`CoreFx` registry pair, `HeroTransformService`/`HeroData` attachment, `BEACON_ACTIVATE` sound.
- **Edge constraints:** "instant cosmetic burst only — no beams, no rings, no screen effects"; "must work identically for every hero — it is a shared transform cue, not hero-specific".

### Rejected / alternative candidates

- `GokuInstantTransmissionAbility` — a second teleport (ki-aura + `PORTAL` + `END_ROD` blink); dropped because 1.6 already covers teleport, but valid if a calmer non-fire teleport look is needed.
- `IronMan` `RepulsorAbility`/`UnibeamController` — repulsor is a `BeamFx` STYLE_REPULSOR tracer (fast travelling head + impact ring via `BeamDraws.repulsorTracer`, `REPULSOR_SPARK` particles); unibeam is a charged chest blast (`UNIBEAM_SPARK` + `SOUL_FIRE_FLAME`/`GLOW`/`ELECTRIC_SPARK`). Good extra beam-family coverage if needed.
- `ATrainSonicBoomAbility` — minimal `SONIC_BOOM` + `CLOUD` burst; too vanilla-thin to be a strong eval row.
- `ThanosSnapAbility` — huge `ModParticles` spread (`purple_flame`/`dark_star`/`soul_spark`/`nightfall`/`chaos_orb`/`sun_particle`/`white_boom`/`black_flame` + `FLASH` + sonic boom) — usable as a "cosmic snap" row if a 13th is wanted.
- `KratosLeviathanThrowAbility` — thrown frost axe (`SNOWFLAKE` trail + `END_ROD` + `EXPLOSION` + glass break); a decent ice-projectile contrast.

---

## 2. Modded resource surface

### 2.1 Particle types — 33 `superheroes:*` ids

All are `FabricParticleTypes.simple()` `SimpleParticleType`s registered into `BuiltInRegistries.PARTICLE_TYPE` with `ModId.of(...)`. Client factories are all `EndRodParticle.Provider` (a vanilla billboard quad on the type's sprite list) except `silent`, whose provider returns `null` on purpose.

| Class (file) | ids (`superheroes:*`) | Client provider (file) |
|---|---|---|
| `src/main/java/.../particle/ModParticles.java` (19) | `transform_spark`, `laser_spark`, `white_boom`, `sword_explosion`, `sparks`, `dark_star`, `purple_flame`, `black_flame`, `dazzling`, `sun_particle`, `soul_spark`, `nightfall`, `chaos_orb`, `anomaly_slice`, `jiwald_effect`, `fula_particle`, `shamak`, `blue_flame`, `moonveil` | `src/client/.../fx/CoreFx.java` — `transform_spark`/`laser_spark` direct `EndRodParticle.Provider::new`; the other 17 wrapped in `CustomParticleGate` (returns `null` when `SuperheroesClientConfig.vfxMode()==LEGACY`, `src/client/.../fx/CustomParticleGate.java`) |
| `src/main/java/.../core/particle/SilentParticles.java` (1) | `silent` | `CoreFx.java` l.57–58 — provider always returns `null` (renders nothing; used to mute vanilla explosion particles when a Visual Core event owns the presentation) |
| `src/main/java/.../hero/captainamerica/registry/CaptainAmericaParticles.java` (2) | `cap_shield_trail`, `cap_shield_slam_burst` | `src/client/.../hero/captainamerica/CaptainAmericaClientModule.java` l.21–22 — EndRod |
| `src/main/java/.../hero/goku/registry/GokuParticles.java` (3) | `goku_ki_aura`, `goku_kamehameha_core`, `goku_kamehameha_trail` | `src/client/.../hero/goku/GokuClientModule.java` l.18–20 — EndRod |
| `src/main/java/.../hero/ironman/registry/IronManParticles.java` (2) | `repulsor_spark`, `unibeam_spark` | `src/client/.../hero/ironman/IronManClientModule.java` l.73–74 — EndRod |
| `src/main/java/.../hero/kratos/registry/KratosParticles.java` (3) | `kratos_hand_burst_1`, `kratos_hand_burst_2`, `kratos_hand_burst_3` | `src/client/.../hero/kratos/KratosClientModule.java` l.24–29 — `CustomParticleGate` over EndRod |
| `src/main/java/.../hero/naruto/registry/NarutoParticles.java` (3) | `naruto_rasengan_swirl`, `naruto_clone_poof`, `naruto_kawarimi_smoke` | `src/client/.../hero/naruto/NarutoClientModule.java` l.21–23 — EndRod |

Hero modules force class-init in `register()` so the types exist server-side. Sprite lists live in `src/main/resources/assets/superheroes/particles/<id>.json` (33 files, one per id); textures in `src/main/resources/assets/superheroes/textures/particle/*.png` (multi-frame sets like `white_boom_1..15`, `sword_explosion_1..5`, `sparks_0..2`, `shamak_1..2`).

### 2.2 Quasar emitters — 15 ids

`src/main/resources/assets/superheroes/quasar/emitters/*.json`:

`homelander_clap_dust`, `homelander_clap_flash`, `homelander_flight_boost`, `homelander_flight_landing`, `homelander_iron_fists_hand`, `homelander_iron_fists_impact`, `homelander_laser_impact`, `homelander_roar_dust`, `homelander_roar_wave`, `homelander_sun_debris`, `homelander_sun_ember`, `scorpion_harpoon`, `scorpion_hellbreath`, `scorpion_hellfire`, `scorpion_teleport`.

Each emitter JSON is thin (`max_lifetime`, `loop`, `rate`, `count`, `emitter_settings{shape, particle_settings}`, `particle_data`) and delegates to modules under `quasar/modules/`: `emitter/particle/` (15), `emitter/shape/` (15), `particle_data/` (15, declares `sprite` PNG + `render_modules`), `render/color/` (5: `hellfire`, `homelander_dust`, `homelander_gold`, `homelander_laser`, `homelander_shock`).

**How a quasar emitter is spawned at runtime:** codex has NO quasar engine of its own — it rides Veil's. `VfxBackend.emit(ResourceLocation, Vec3)` → `VeilVfxBackend.emit` (`src/client/.../core/vfx/veil/VeilVfxBackend.java` l.48–60): `VeilRenderSystem.renderer().getParticleManager().createEmitter(id)` → `emitter.setPosition(pos)` → `manager.addParticleSystem(emitter)`. The resource path convention is `assets/<ns>/quasar/emitters/<emitter>.json` (`VfxBackend` javadoc l.14). Scorpion's FX do the same directly through `VeilScorpionFx.spawn` (`src/client/.../scorpion/fx/veil/VeilScorpionFx.java` l.48–59).

**Veil requirement:** quasar emitters REQUIRE Veil. `VfxBackends.resolve()` (`client/core/vfx/backend/VfxBackends.java` l.37–49) instantiates `VeilVfxBackend` reflectively only when `FabricLoader.isModLoaded("veil")`, else `FallbackVfxBackend`. On fallback: `emit` → **silent no-op**, `light` → noop handle, `distortion` → dropped, `flash` → HUD overlay fill (`FallbackVfxBackend` l.32–48 + `renderFlashHud`). `ClientScorpionFx.play` returns early entirely when Veil is absent (`ClientScorpionFx.java` l.17–24 — server-side vanilla particles still cover the look). Net degradation without Veil: no quasar emitter bursts, no dynamic lights, no post-pipeline flash/distortion; `ShockwavePattern`/`TrailPattern`/`BeamPattern` renders, sounds, shakes, vanilla particles and HUD flash still work. `VfxQuasarResourcesParseTest` (`src/test/.../assets/VfxQuasarResourcesParseTest.java`) validates every quasar JSON parses.

### 2.3 Other VFX assets and their consumers

- `assets/superheroes/vfx/**/*.json` (8 files: `flight/pose.json`, `homelander/{clap,flight,iron_fists,laser,roar,sun_charge,sun_detonation}.json`) — `VfxParams` tuning consumed by `VfxParamsLoader` (§0). `flight/pose.json` is read by `FlightPoseTracker` via id `superheroes:flight/pose` (pose math: pitch curves, roll, loop-sound scaling).
- `textures/vfx/homelander/{ember,laser_core,laser_glow,shock_ring,sun_flash,sun_ring}.png` — quasar sprite sources referenced by `particle_data` modules (e.g. `homelander_clap_flash` → `shock_ring.png`, `homelander_laser_impact` → `laser_glow.png`, iron fists → `ember.png`, `homelander_roar_wave` → `shock_ring.png`); `sun_detonation.json` params reference the `sun_*` tuning knobs.
- `textures/effect/soft_trail.png` — `TrailPattern.soft` ribbons in `FlightFx` (l.59–60). `textures/effect/homelander/laser_scorch.png` — `ScorchMarkRenderer` decal quads (`src/client/.../fx/ScorchMarkRenderer.java`, data via `core/net/ScorchMarksS2CPayload` → `ScorchMarkStore`).
- `pinwheel/post/{vfx_flash,vfx_distortion}.json` + `pinwheel/shaders/program/vfx/{flash,distortion}.{fsh,json}` — Veil post pipelines driven by `VeilPostEffects` (uniforms `uIntensity`, `uColor`, `uCenter`, `uRadius`, `uStrength`; armed per tick then auto-removed at zero intensity). Fallback: flash → HUD fill; distortion → dropped.
- `textures/particle/*.png` (33+ frames) — sprite sources for §2.1 types.
- Sounds: `HomelanderSounds` (15 `homelander.*` events, `src/main/.../sound/HomelanderSounds.java`), `ScorpionSounds` (`get_over_here` etc.), plus heavy use of vanilla `SoundEvents` across abilities.

---

## 3. Load-as-dependency facts

**Declared deps — `src/main/resources/fabric.mod.json`:**

```json
"depends": {
  "fabricloader": ">=0.19.2",
  "minecraft": "~1.21.1",
  "java": ">=21",
  "fabric-api": ">=0.116.12",
  "geckolib": ">=4.5.0",
  "entity_model_features": ">=3.3"
},
"recommends": { "veil": ">=4.1.2" }
```

`"environment": "*"`; entrypoints `main`/`client`/`fabric-datagen`; mixin configs `superheroes.mixins.json` + `superheroes.compat.mixins.json` (both envs) and `superheroes.client.mixins.json` + `superheroes.client.core.mixins.json` gated `"environment": "client"`.

**Versions — `gradle.properties`:** minecraft 1.21.1, loader 0.19.2, loom 1.16-SNAPSHOT, mod_version **4.7.0**, fabric_api 0.116.12+1.21.1, veil 4.1.2. Java 21 (build comment notes system default is 17; CI uses Temurin 21).

**Actual jar dependencies — `build.gradle`:**

- **Bundled inside the shipped jar (jar-in-jar, no separate install needed):** `software.bernie.geckolib:geckolib-fabric-1.21:4.5.8`, `maven.modrinth:entity-model-features:3.3.9-fabric-1.21`, `maven.modrinth:entitytexturefeatures:7.2.4-fabric-1.21` (ETF is EMF's own dep, bundled alongside).
- **NOT bundled — must exist in the host env:** `net.fabricmc:fabric-loader ≥0.19.2`, `net.fabricmc.fabric-api:fabric-api ≥0.116.12+1.21.1`.
- **Optional:** `foundry.veil:veil-fabric-1.21.1:4.1.2` (`modImplementation` only — deliberately not `include`d; every use is behind `isModLoaded("veil")`), `maven.modrinth:iris:1.8.8+1.21.1-fabric` (`modCompileOnly` — Mirror Dimension's Acid-shaderpack toggle only; guarded by `isModLoaded("iris")`).
- **No** trinkets / architectury / cloth-config / cardinal-components dependencies anywhere.

**Headless / gametest safety:** the mod itself runs a dedicated-server GameTest suite (`./gradlew runGametest`, 20+ test classes under `src/gametest`, wired via `-Dfabric-api.gametest`), and `ProjectSanityTest` asserts `src/main` is server-safe — so loading `superheroes` into a headless dev env does not crash: the `client` entrypoint and client mixins never load server-side, `veil.*` exists only under `src/client` behind `isModLoaded`, and on a dedicated server the bundled client-only EMF/ETF nested jars land in `envDisabledMods` (the `entity_model_features` depends softens to suggests — noted in `build.gradle` l.227–232). A `servernoveil` source set exists purely to prove the veil-free server classpath (build.gradle l.75–85).

**Building the jar:** `./gradlew assemble --no-daemon` → `build/libs/superheroes-4.7.0.jar` (jar name = `superheroes-<mod_version>`; requires Java 21 — Maven Central 429s are worked around via `~/.gradle/init.d/central-mirror.gradle` rewriting to the GCS mirror). With `-PmcpUpstreamJar=<path>` the same `assemble` also produces `build/libs/superheroes-mcpdev-4.7.0.jar`.

---

## 4. `src/mcpdev` notes (reference only)

`src/mcpdev` is a second, dev-only mod `codex-mcpdev` that glues the chapmanjw Minecraft MCP bridge (`com.chapmanjw.minecraft.fabric.mcp.*`) to codex without the main mod ever importing MCP types — coupling direction is `mcpdev → {main, upstream}`. `build.gradle` (l.99–150) reads the Gradle property `mcpUpstreamJar`: when `-PmcpUpstreamJar=<path-to-upstream-mcp-jar>` is passed, `mcpdevCompileOnly files(...)` plus compile-only `jackson-databind/core/annotations:2.22.x` (runtime copies come from the MCP mod's own bundled jars) activate the whole source set, every `mcpdev` task carries `onlyIf { mcpCompanionEnabled }`, and `jarMcpdev` emits `superheroes-mcpdev-<version>.jar` as part of `assemble`; without the property the source set is fully dormant and skipped. At runtime its `fabric.mod.json` declares two entrypoints: `main` → `CodexMcpdevBridge` (a `ModInitializer` that just caches the live `MinecraftServer` via `ServerLifecycleEvents` for the tools), and `mcp-tools` → `CodexMcpdevToolProvider` (implements upstream `ToolProvider`, contributes six `codex_*` tools — `CodexAbilityInvokeTool`, `CodexAbilityListTool`, `CodexCooldownsClearTool`, `CodexHeroListTool`, `CodexHeroSelectTool`, `CodexModStatusTool` — and declares the `codex` domain → `ToolCategory.SERVER` because the upstream filter rejects unknown domains). `depends` in its fmj is `superheroes:*`, `fabric-api:*`, `fabricloader>=0.19.2`, `minecraft~1.21.1` — the companion is never shipped.
