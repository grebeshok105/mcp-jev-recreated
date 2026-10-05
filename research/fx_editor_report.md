# Photon .fx editor-layer — implementation report

Stage 2 of the editor investigation. Stage 1 (`editor_need_report.md`) proved a **narrow** editor is needed; this report covers the layer that was built and live-verified.

## 1. Real .fx layout (verified against Photon sources + stock files)

`.fx` = gzip'd Minecraft NBT (`NbtIo.readCompressed`). Root compound `""` → `{version:int, fxData:{fxObjects:[...]}}` — `version` is a root-level sibling of `fxData`, not inside it. Each fxObject = `{type:"beam_emitter|particle_emitter|trail_emitter|ara_trail_emitter|empty", data:{name, transform:{id,_parentId,_childrenId,localPosition/localScale/localRotation}, config:{...}}}`.

Config internals: plain scalars (`duration:int`, `maxParticles:int`, `minVertexDistance:float`, `end:list[float]`), enum strings (`simulationSpace`, `emissionMode`, `layer`), NumberFunction wrappers `{type: constant|random_constant|color|gradient|random_color|random_gradient|curve|random_curve, data:{number:<scalar or ARGB int>}}`, and `_enable:byte` feature-layer compounds (lights, trails, uvAnimation, physics, noise, *OverLifetime, inheritVelocity, subEmitters, …). `emission` holds `emissionRate`/`distanceRate` numfuncs + `bursts.payload[i]` (probability/count/cycles/interval/time — `random.nextFloat() < probability` gate, so 0 suppresses a burst cleanly).

## 2. What is editable

Three op classes, matched exactly to the stage-1 blocker list:

- **scalar** — constant number functions (int/float tag type preserved), plain numerics, vec3 float lists, enum strings; nested dot-paths with `[i]` list slots (`emission.bursts.payload[0].probability`).
- **color/tint** — `#RRGGBB`/`#AARRGGBB` → ARGB int into `type: color` number functions.
- **toggle** — layer `_enable` bytes (lights, trails, physics, …), plus whole-emitter removal (`emitter:N`) with parent/child id scrubbing. `selfVisible` is runtime-only, not serialized — removal is the only whole-emitter disable.

Refused with per-op errors (never guessed): non-constant number functions, unknown paths, type mismatches, last-emitter removal, re-adding emitters.

## 3. MCP tools added

`src/jevlab/fx_nbt.py` (minimal NBT codec), `src/jevlab/fx_edit.py` (editor core), 5 tools in `mcp_server.py`:

- `vfx_fx_inspect(id)` — normalized emitters/fields/layers, each field tagged patchable or not.
- `vfx_fx_clone(src, new_id, ops?)` — new resource id, fresh uuids, provenance sidecar; original never touched.
- `vfx_fx_patch(id, ops)` — semantic ops on a clone.
- `vfx_fx_validate(id)` — structural gate, errors vs warnings.
- `vfx_fx_register(id)` — catalog passport (`kind: fx`, `ready_to_use`, `source: fx-edit`); index cache reset so find/scene see it immediately.

## 4. Clone/patch examples (actually executed)

```json
clone vfxlab:laser_beam → vfxlab:laser_beam_red
  color "#FF2222"  (#ff33ccff cyan → red)
  width 0.35       (0.12 → ~3x thicker)
  duration 60      (120 → half)

clone vfxlab:ember_ring_burst → vfxlab:ember_ring_burst_noburst
  emission.bursts.payload[0].probability 0.0
```

## 5. Live playback results

Two compare scenes, originals and clones side by side, real client playback (`vfxlab.4_scene`, PASS both runs):

- **beam**: `threequarter__t10` frame shows fat RED beam next to thin CYAN beam — color and width patches rendered by Photon. Frames: `research/frames/*_v3.png`.
- **ring**: original fires its 60-ember burst arc; clone emits only the slow `emissionRate` trickle — `spawned` counts confirm (top angle 64 = 60 orig + ~4 clone). Frames: `research/frames/*ring_compare*`.

No hot reload needed — playback launches a fresh client each run; new `.fx` in `probe/src/main/resources` resolve automatically.

## 6. What was harder than expected

- **Semantic flattening**: `.fx` config nests number functions and `_enable` layers arbitrarily; needed a walk that classifies each leaf (numfunc vs vec vs enum vs layer) and recurses list-of-compound payloads (bursts) — took two iterations to expose burst fields.
- **Whole-emitter disable**: no serialized flag exists; implemented as fxObject removal + `_childrenId`/`_parentId` scrub.
- **Camera framing for proof**: beams render ~+0.5 above spawn and extend +x — first compare scene cropped them; second had the clone under the camera; third with x-separation worked.

## 7. Remaining limits

- No node graph edits, no curves/gradients editing, no textures/materials — by design.
- `toggle` cannot re-add a removed emitter; layer ops only flip `_enable`, not per-component scalar params deep inside (they're reachable via scalar paths if constant).
- Clone passports inherit source `measured`/`visual` — re-capture needed if the patch changes selection-relevant appearance.
- `fx_validate` is structural only; runtime acceptance proven by playback (as required).

## 8. Was graph-level access needed anywhere?

**No.** Zero cases required reading or editing node structure. Every blocker from stage 1 mapped to scalar/color/toggle. The dispatch codec (`fxObjects[].type`) is flat — there is no internal graph in the file format at all; "nodes" exist only in the Photon GUI editor.

## 9. Originals unmutated

Confirmed: `git status` shows no changes to the 5 stock `.fx` files (tracked, unchanged hashes), and `patch_fx`/`clone_fx` never write to source paths — unit test `test_clone_never_mutates_source` asserts sha256 before/after.

## 10. Is a full graph editor still worth thinking about?

No — and it never was the right frame. The file has no graph; what stage 1 needed was parameter access. The 5-tool lane covers the patchable share of logged wants (6 of 8 directly; the rest needed catalog assets, not patching). The only uncovered stage-1 blocker (melee slash vocab) is a **catalog gap** (no visible slash resource to clone from), which no editor layer fixes — it needs new source assets.
