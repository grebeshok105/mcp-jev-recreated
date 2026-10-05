---
name: vfxlab-scenes
description: Write and refine .scene.json specs (grammar v2) and run exact real-client playback in mcp-jev-recreated. Use when staging multiple VFX resources on a tick timeline; working with anchors (player head/chest/look, camera, scene, ref:), directions, follow, pos/rotation/scale tracks, repeat/groups, cross-step refs, or tick commands; validating with vfx_scene_validate/plan and iterating on captured frames and timings.
---

# vfxlab Scenes

Author scene specs that stage catalog resources on one tick timeline and replay them in the real Minecraft 1.21.1 client. Quality comes from anchor/direction correctness, timing design, and inspecting the actual returned frames.

## Bootstrap

This is one of 3 vfxlab skills. If you have not already loaded them this session, load the other two now — `vfxlab-use` (orchestration + safety rules) and `vfxlab-pipeline` (how to find/preview resource ids) — then continue.

## One spec → one runtime

The probe scenario `vfxlab.4_scene` is the **only** runtime; preview and gameplay replay the identical deterministic timeline per camera angle. Validation states honestly what the runtime cannot do — never invent an editor-only interpretation. Canonical example: `examples/follow_beam.scene.json`; simpler: `examples/roar_burst.scene.json`.

## Authoring loop

```
pick ids (vfx_find/vfx_preview) → write spec → vfx_scene_validate
→ vfx_scene_plan → vfx_scene_play → read the actual frames → fix timings → repeat
```

`vfx_scene_play` writes `data/capture/scene/scene_plan.json`, runs `runUitest -Pvfxlab.uitestSelection=vfxlab.4_scene` under xvfb (Java 21 at `~/.jdks/temurin-21` or `$VFXLAB_JAVA_HOME`; ~40–60 s+), and returns `scene_results.json` + frame paths (`scene_frames_index.json`).

## Spec shape

```json
{"name": "demo", "duration": 40, "frames": [9, 20],
 "scene": {"pos": [8.5, 2.0, 8.5], "time": 6000, "weather": "clear"},
 "camera": {"angles": ["front", "top"]},
 "steps": [
   {"tick": 2, "id": "minecraft:dust", "name": "mark",
    "anchor": "scene", "offset": [0, 0.8, 0],
    "options": {"color": [1,0.15,0.15], "scale": 2}},
   {"tick": 10, "id": "vfxlab:laser_beam",
    "anchor": "player.head", "to": "ref:mark", "follow": "player"}
 ],
 "groups": [{"tick": 18, "repeat": {"every": 12, "count": 2},
   "steps": [{"tick": 0, "id": "minecraft:sonic_boom",
              "anchor": "scene", "offset": [0,1.2,0]}]}],
 "commands": [{"tick": 26, "command": "execute at @p run tp @p ~2 ~ ~ ~30 ~"}]}
```

## Field reference

| field | values |
|---|---|
| `anchor` | `scene` \| `player` (feet) \| `player.chest` \| `player.head` \| `player.look` \| `camera` \| `ref:<step name>`; or `{anchor, offset, direction, distance}` |
| `offset` | `[x,y,z]` in the resolved direction's **local** frame |
| `distance` | extra blocks along the direction; a `distance` with no explicit direction on a player/camera anchor injects `player.look` |
| `direction` | `world` \| `player.look` \| `[yaw,pitch]` \| `{"face": <anchor expr>}` |
| `to` | face a target point; explicit `direction` wins over `to` (validator warns) |
| `pos` | extra offset in the **anchor** frame (not rotated by direction) |
| `follow` | `"player"` re-resolves the anchor every tick — persistent kinds only (`fx`, `quasar_emitter`) |
| `track` | `pos` keyframes `[t,x,y,z]` (fx + quasar, local-frame deltas from the anchor); `rotation` `[t,yaw,pitch]` and `scale` `[t,s]` — **fx only**; keyframe ticks are relative to the step's spawn |
| `repeat` | `{every, count}` \| `{every, until}` on a step or a whole `groups[]` block; expanded at compile time |
| `options` | per-resource spawn params; `ref:<name>` substitutes a named step's position |
| `commands` | `[{tick, command}]` server-side commands mid-scene |

Aliases: `player.head` = `player.look` = `camera`; bare `player` = feet.

## Semantics that bite

- `repeat.count` **includes the first firing**; `repeat.until` is an **absolute** tick (`t < until`), including inside repeated groups. `until <= tick` fires once + warns.
- Member ticks inside `groups[]` are **relative to the group tick**; group repeat re-fires the whole block. Repeat tails past `duration` are dropped with a warning.
- `ref:` producers must sort **before** consumers in the step stream (same tick is fine if earlier). Refs record the **spawn-time** position — a followed emitter's later motion does not flow into `ref:` consumers. `ref:` must be the whole option value; nesting it inside a list/dict is an error. Duplicate names → most recently spawned instance wins.
- `commands` run in **console context**: `~` resolves at world spawn, not the player — use `execute at @p` for player-relative moves. Per angle the ordering is drive → commands → spawn; a `tp` lands on the *next* tick's player position. Commands replay once per angle.
- `pos`/`offset` rotate with the resolved direction; `track.pos` rows are local-frame deltas.
- fx roots render **~0.5 blocks above `at`** — deliberate photon centering that all 197 captures were measured with; do not "fix" it.
- `stop_after: false` deliberately leaks a persistent handle into the next angle (emitted honestly, not clamped).
- Unknown keys at every level warn instead of silently dropping (`anchr:` typos surface); a bool where an int is expected errors.
- `tick: 0` fires at scene start. `camera.angles` known: front, back, side, side_right, top, threequarter, low, far; duplicates warn (a replay overwrites the first run's results).

## Errors vs warnings

**Errors:** unknown resource id; not `ready_to_use`; non-spawnable kind (composite/texture/shader/mesh); `world_event` without `has_visual`; unresolvable required params; `ref:` to a later/nonexistent step; `rotation`/`scale` track on a quasar emitter; frames/duration/type violations.
**Warnings:** `requires_water` / `capture_failed` passports (real effects, limited capture environment); `follow` or `track` on instantaneous kinds (nothing to drive — honest "no channel" warning); `direction` + `to` together; `until <= tick`; repeat tail past duration; duplicate frames/angles; unknown keys.

## Runtime gotchas (verified)

- **In the probe the player IS the camera** — player-anchored effects land at the viewpoint. Keep them in frame with a look-frame offset (`offset: [0, -0.5, 2.0]` = ahead and slightly below the eye line) or use `scene`/`ref:` anchors.
- Quasar emitters steer via `ParticleEmitter.setPosition`; fx via `root.updatePos/updateRotation/updateScale`. `particle`/`level_event` are instantaneous — `follow`/`track` can only warn.
- Some emitters legitimately render nothing at eye level (documented `capture_failed:offscreen` passports — e.g. ground-scatter quasar shots). Check `vfx_preview` before blaming the spec; pick another angle (`top`) or another resource.

## Visual completion gate

Playback finishing is not proof the scene looks right. Per iteration:

- Read the returned frame paths and **look at the actual PNGs**, per angle — do not judge from spawn counts alone.
- Check what the spec intended vs what pixels show: anchoring (head/chest/look), aim (`to:`/`face:`), follow-through after teleports, repeat cadence, ref wiring.
- Adjust timings/offsets and replay; count honest rounds (a pass that found nothing wrong still counts, a run you never looked at does not).
- Report spawned counts **and** what the frames showed; state explicitly if a step spawned but rendered off-frame.
