---
name: vfxlab-fx-edit
description: "Clone and safely customize Photon .fx resources in mcp-jev-recreated via vfx_fx_inspect/clone/patch/validate/register. Use when a suitable stock .fx exists but needs a semantic tweak — recolor, resize, retime, or disabling one emitter/layer — before it goes into scenes. Never use for choreography (that is vfxlab-scenes), arbitrary node edits, curves, textures, or building effects from scratch."
---

# vfxlab FX Edit

Narrow customization lane for Photon `.fx` resources: clone a good stock effect, patch a few semantic parameters, register it, and use it in the normal VFXLab flow.

## Bootstrap

This is one of 4 vfxlab skills. If you have not already loaded them this session, load the other three now — `vfxlab-use`, `vfxlab-scenes`, `vfxlab-pipeline` — then continue. The same rule is stated at the top of each skill; already-loaded skills do not need re-loading.

## When this lane applies vs. when it does not

The scene grammar and the catalog solve most staging problems. Reach for the editor **only** after choreography is ruled out.

Use `vfxlab-fx-edit` when ALL of these hold:

1. You already found a `.fx` that is *visually right in principle* (previewed/measured, not just named right).
2. The gap is in the **resource itself**: wrong color, wrong size/width/length, wrong duration/lifetime, a layer you want off (lights, trail, noise…), or one emitter of several you want removed.
3. Scene grammar cannot express it — anchors, directions, tracks, repeat, commands never change *what a resource looks like*, only where/when it plays.

Do NOT use the editor when:

- The first scene result merely "looks weak" — fix choreography first (positions, timings, layering, counts). A mis-staged good resource is still a good resource.
- The effect needs different *movement/sequencing* — that is `vfxlab-scenes`.
- No suitable `.fx` exists — cloning nothing good produces nothing good; that is a catalog gap, not an editing task.
- You want to add/remove/reconnect nodes, edit curves or materials, swap textures, or rebuild internal choreography — all intentionally unsupported. Ask for a different resource or report the gap.

## Tool flow

`vfx_fx_inspect` → `vfx_fx_clone` → `vfx_fx_patch` → `vfx_fx_validate` → `vfx_fx_register` → normal `vfx_find` / `vfx_inspect` / `vfx_preview` / `vfx_scene_*` on the clone.

- **`vfx_fx_inspect(id)`** — normalized emitter view. Each emitter lists `fields` (path → `{kind, value, patchable}`) and `layers` (`_enable` feature compounds). Read this before patching: only `patchable` entries accept ops.
- **`vfx_fx_clone(src, new_id, ops?)`** — writes a new `.fx` under `assets/<ns>/fx/` (src resources + runtime mirror), fresh transform uuids, provenance sidecar in `data/fx_provenance/`. The source is never mutated. `ops` may apply patches atomically at clone time.
- **`vfx_fx_patch(id, ops)`** — apply ops to an existing resource. Use it on clones; never patch stock fixtures.
- **`vfx_fx_validate(id)`** — structural gate: NBT reads, `fxData.fxObjects` well-formed, known types, unique transform ids. `errors` block; `warnings` inform.
- **`vfx_fx_register(id)`** — adds a catalog passport (`kind: fx`, `ready_to_use`, `source: fx-edit`) inheriting the source's factual/measured/visual data with `fx_clone` provenance. After this the id works everywhere stock ids do.

## Op vocabulary (the whole supported set)

```json
{"op": "scalar", "emitter": "0",     "field": "width",            "value": 0.35}
{"op": "scalar", "emitter": "0",     "field": "end",              "value": [4, 0.5, 0]}
{"op": "scalar", "emitter": "0",     "field": "emission.bursts.payload[0].probability", "value": 0.0}
{"op": "color",  "emitter": "0",     "field": "color",            "value": "#FF2222"}
{"op": "toggle", "emitter": "0",     "field": "lights",           "value": false}
{"op": "toggle", "emitter": "emitter:0",                          "value": false}
```

- `emitter` selects by index (`"0"`, `"1"`…) or by its `name` field. `"emitter:0"` targets the whole object.
- **scalar** writes constant number-functions (keeping int/float tag type), plain int/float fields, vec3 float lists, and enum strings. Nested paths use dots + `[i]` list slots (`emission.bursts.payload[0].count`).
- **color** takes `#RRGGBB` or `#AARRGGBB`, stored as an ARGB int in `type: color` number functions.
- **toggle on a layer** flips its `_enable` byte (lights, trails, uvAnimation, physics, noise, *OverLifetime, subEmitters, …). **toggle on `emitter:N`** removes that fxObject and scrubs parent/child references — refused when it is the last emitter (empty `.fx` plays nothing) and re-adding a removed emitter is not supported.
- Anything else — non-constant number functions (curve, gradient, random_*), unknown paths, type mismatches — returns a per-op error and writes nothing. The tool reports; it never guesses.

## Rules that keep clones honest

1. **Originals stay untouched** — clone first, always. `clone_fx` + tests enforce it.
2. **Register before use** — an unregistered clone exists on disk but scenes/Jev cannot see it.
3. **Validate structurally, prove visually** — `fx_validate` catches corrupt structure; only a `vfx_scene_play` run proves Photon accepts and renders the change. Compare clone vs source frames side by side (spawn both in one scene a few blocks apart).
4. **Provenance travels** — the provenance file + passport `fx_clone` block record source id, ops, and date. Keep them when copying clone workflows into docs.
5. **Inherited passport data is the source's** — `measured`/`visual` on a clone describe the original capture, not the patch; re-capture if the difference matters to selection.

## Known limits (by design)

- No graph/node edits, no new emitters, no curve/material/texture changes.
- Round-trip is byte-identical for unmodified sections, but field *ordering* inside edited compounds may differ from Photon-authored files — semantically irrelevant to the loader.
- No hot reload: playback launches a fresh client, so new `.fx` resolve on the next run automatically.
