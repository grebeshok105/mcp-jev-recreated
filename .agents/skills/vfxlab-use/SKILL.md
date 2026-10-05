---
name: vfxlab-use
description: "MANDATORY prerequisite — invoke BEFORE any vfx_* MCP tool call, jevlab pipeline command, or scene/capture work in mcp-jev-recreated. Orchestrates the other vfxlab-* skills. Trigger on: finding/selecting Minecraft VFX resources by description, writing or debugging .scene.json specs, running scene playback/captures/evals, rebuilding the catalog, calls to vfx_find/vfx_inspect/vfx_preview/vfx_scene_* tools. Dispatches to the right sub-skill, enforces pre-flight checks (catalog, API key, Java+xvfb), and keeps every claim measured and capture-honest."
---

# vfxlab Use

Orchestrator for the vfxlab system — VFX Knowledge Base + Jev selector + real-client scene playback, in this repo (`mcp-jev-recreated`). Load this **before** touching effects, scenes, or the pipeline.

## Bootstrap

This is one of 4 vfxlab skills. If you have not already loaded them this session, load the other three now — `vfxlab-scenes`, `vfxlab-pipeline` and `vfxlab-fx-edit` — then continue. The same rule is stated at the top of each skill; already-loaded skills do not need re-loading.

## Rule

Any request that will call a `vfx_*` MCP tool or run a jevlab pipeline command **must** go through this skill first.

Steps, in order:

1. **Classify the request** → pick one or more sub-skills (table below).
2. **Pre-flight** → confirm catalog, credentials, runtime prereqs (see "Pre-flight checks").
3. **Load the sub-skill(s)** via the Skill tool.
4. **Execute** the sub-skill's workflow.
5. **Close the loop** → validate / play / read frames / eval — and report only measured numbers.

## Skill routing table

Pick by primary intent. When the task spans domains, load **all** relevant skills before starting.

| User intent | Primary skill | Also load when… |
|---|---|---|
| Write/debug a `.scene.json`; anchors, directions, follow, tracks, repeat, refs, commands; run playback; read scene frames | `vfxlab-scenes` | resources not picked yet → `vfxlab-pipeline` (find/inspect/preview) |
| "find an effect for X", rank candidates, inspect passports, preview captured frames, run evals | `vfxlab-pipeline` | results get staged → `vfxlab-scenes` |
| Run captures, contact sheets, visual annotation passes, rebuild catalog, operate `jevlab-mcp` | `vfxlab-pipeline` | — |
| Stock `.fx` is right but needs recolor/resize/retime or one emitter/layer off — clone + semantic patch, then back into scenes | `vfxlab-fx-edit` | choreography still open → `vfxlab-scenes` first |
| "What is this repo / how does it fit together" | this skill + the `vfxlab-pipeline` reference tables | — |

Routing rule for edits: try scene grammar before `.fx` edits. The editor only operates on an already-found suitable resource; a weak first scene is a choreography problem until proven otherwise. See `vfxlab-fx-edit` for the apply/do-not-apply checklist.

## Pre-flight checks

Run before any pipeline operation:

1. **Catalog present and fresh?** `data/catalog.json` — 4,430 passports, 205 answerable. Rebuild via `vfxlab-pipeline` if stale.
2. **Jev needed?** `vfx_find` / evals call the real TypeSafe API — requires `TYPESAFE_API_KEY` in env.
3. **Client run needed?** Playback/capture = real Minecraft 1.21.1 client under xvfb — needs Java 21 (`~/.jdks/temurin-21` or `$VFXLAB_JAVA_HOME`) and `xvfb-run`; a scene replay takes ~40–60 s+.
4. **Kind check.** Only `ready_to_use` + spawnable kinds stage in scenes: `particle`, `parameterized_particle`, `world_event` (needs `has_visual`), `fx`, `quasar_emitter`. `composite`/`texture`/`shader`/`mesh` stay KB-only — validation rejects them.

## Safety & honesty rules (apply in every session)

1. **Never infer visuals from names or metadata.** Visual semantics come only from real captured frames. Passport `visual_status` says whether a capture is trustworthy: `observed` vs `capture_failed:*` / `environment_mismatch:*`. A capture that saw nothing is a property of the capture, not of the effect.
2. **Measured numbers only.** Report counts/recalls/latencies actually produced by a run this session or committed under `data/`+docs — never estimate.
3. **One spec → one runtime.** The probe (`vfxlab.4_scene`) is the only playback runtime; preview and gameplay replay the identical timeline. No editor-only interpretations — validation already states honestly what the runtime cannot do.
4. **Errors vs warnings are deliberate.** `requires_water` / `capture_failed` passports warn (the effect is real; the environment limited capture). Unknown ids, non-spawnable kinds, unresolvable params, bad refs error.
5. **Deterministic replay.** Same timeline every camera angle; commands replay once per angle; a replay overwrites that angle's earlier results.

## What this skill does NOT cover

- Photon/LDLib2 mod development — that repo's own docs.
- Changing the TypeSafe/Jev client contract — read `src/jevlab/jev/client.py` first.
