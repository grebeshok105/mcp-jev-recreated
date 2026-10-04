# Photon `1.21.1-fabric-2.2` — FX engine inventory

Source analysis of `github.com/grebeshok105/Photon` @ `1.21.1-fabric-2.2` (HEAD `e97d9bd`), module `com.lowdragmc.photon`, checkout `/home/ubuntu/repos/Photon`. No code was run or modified. All paths below are relative to `src/main/java/` unless they start `src/main/resources/`. Companion library `com.lowdragmc.lowdraglib2` (LDLib2) is referenced from the vendored `libs/ldlib2-fabric-1.21.1-2.7.jar`.

## 1. Primitive taxonomy

FX objects register in the string-keyed registry `photon:fx_object` (`PhotonRegistries.FX_OBJECTS`, `src/main/java/com/lowdragmc/photon/PhotonRegistries.java`). The registry is filled by scanning `@LDLRegisterClient(registry = "photon:fx_object")` static `FXObjectType TYPE` fields. **Exactly 6 object types exist** — there are no text, light, transformer, or standalone mesh-model object types (meshes are a *render mode* of emitters, see `ParticleRendererSetting.Mode.Model`).

| Type id | Class | Render character | Programmatic? |
|---|---|---|---|
| `empty` | `client/gameobject/EmptyFXObject.java` | non-rendering container/node; doubles as the FXRuntime root object (`FXRuntime.ROOT_UUID`) and as the parent for grouping children in the editor hierarchy | yes — trivial no-arg |
| `particle_emitter` | `client/gameobject/emitter/particle/ParticleEmitter.java` | quad/model particle system; CPU or GPU-instanced path | yes — `new ParticleEmitter()` / `new ParticleEmitter(ParticleConfig)` |
| `beam_emitter` | `client/gameobject/emitter/beam/BeamEmitter.java` | strip beam between emitter origin and `end` point | yes — `new BeamEmitter()` / `(BeamConfig)` |
| `trail_emitter` | `client/gameobject/emitter/trail/TrailEmitter.java` | ribbon trail following the emitter's motion | yes — `new TrailEmitter()` / `(TrailConfig)` |
| `ara_trail_emitter` | `client/gameobject/emitter/aratrail/AraTrailEmitter.java` | Ara-style volumetric trail (instanced triangle strip, ribbon sections) | yes — `new AraTrailEmitter()` / `(AraTrailConfig)` |
| `force_field` | `client/gameobject/forcefield/ForceFieldObject.java` | invisible field; not rendered itself — it *affects sibling emitters* through their `externalForces` module | yes — `new ForceFieldObject()` |

`ParticleEmitter.TYPE.version() == 2` (datafixer-relevant); all others are `version() == 0`. `EmptyFXObject` registers with priority `-99` (loaded first so runtime root resolution is stable).

Class hierarchy: `EmptyFXObject`/emitter types/force field → `FXObject` (`client/gameobject/FXObject.java`) → vanilla `net.minecraft.client.particle.Particle`. FXObjects therefore *are* particles: they enter `ParticleEngine`'s queue and tick on the client thread. `FXObject` carries `@Persisted` `name` + `transform` (position/rotation/scale), a start-`delay` counter, hierarchy semantics (`isAlive/isPlaying/isVisible/isActive` via `parent`/`children` in `IFXObject`), and `NO_RENDER_RENDER_TYPE` — a static `ParticleRenderType` whose `pipeline` is a `RenderPassPipeline`.

### 1.1 `ParticleConfig` (`emitter/particle/ParticleConfig.java`) — passport fields

Top level (all `@Persisted` unless noted): `duration` (default 100), `looping` (true), `prewarm`, `startDelay` (int ticks), `startLifetime`, `startSpeed`, `startSize` (`NumberFunction3`), `startRotation` (`NumberFunction3`), `startColor` (`Color`), `simulationSpace` enum `Local|World|Custom` + `customSpace` (`TransformRef`), `maxParticles` (2000), `parallelUpdate` (CPU parallel sim ≥128 particles).
Sub-groups (each a persisted setting object):

- `emission` (`EmissionSetting`): `emissionRate`, `distanceRate`, `emissionMode` (`Exacting|Random`), `bursts` list of `Burst{time, count(NumberFunction), cycles, interval, probability}`.
- `shape` (`IShape` + transform/rotation/scale).
- `renderer` (`ParticleRendererSetting`, `emitter/particle/ParticleRendererSetting.java`): `renderMode` enum `Billboard|Horizontal|Vertical|VerticalBillboard|StretchedBillboard|Model` (quaternion factories against `TileParticle`+`Camera`), `useGPUInstance`, `layer` (`RendererSetting.Layer` `Opaque|Translucent`), `sortMode` (`NONE|DISTANCE`), `cull`, `depthMask`, `materials` list (`MaterialSetting`), `model` (`MeshData`), `fixedLight` overrides etc.
- `physics`: gravity, friction/damping, `collision` (block collision + kill/bounce flags), wind.
- `lights`: `fixedLight` and related lighting overrides.
- `velocityOverLifetime`, `inheritVelocity`, `lifetimeByEmitterSpeed`, `forceOverLifetime`, `externalForces` (force-field consumers), `colorOverLifetime`, `colorBySpeed`, `sizeOverLifetime`, `sizeBySpeed`, `rotationOverLifetime`, `rotationBySpeed`, `noise`, `uvAnimation` (texture-sheet animation: tiles/cycles/fps), `trails` (per-particle ribbon trails), `subEmitters`, `additionalGPUDataSetting`.
- `SubEmittersSetting.Emitter`: `fxLocation` (`ResourceLocation` of another FX), `event` (`Birth|Death|Collision|FirstCollision|Tick`), `emitProbability`, `tickInterval`, `inheritColor/Size/Rotation/Lifetime/Duration`. Runtime: `FXHelper.getFX(fxLocation).createRuntime()` re-parented at particle position via `runtime.emit(father.getEmitter().getEffectExecutor())`, deferred to the game thread (`SubEmittersSetting.scheduleSubEmitterSpawn`).

`ParticleEmitter` also carries the giant `RUNTIME_BINDINGS` list — every timeline-animatable config path (`emission.emissionRate`, `physics.gravity`, `renderer.useGPUInstance`, `trails.*`, `uvAnimation.*`, …) — this is the authoritative list of what a timeline `animation` track can animate, and effectively the per-field passport schema.

### 1.2 `BeamConfig` (`emitter/beam/BeamConfig.java`)

`duration`, `looping`, `startDelay` (int), `end` (`Vector3f` target point — beam goes origin→end), `width`, `emitRate` (NumberFunction — particle spawn rate along the beam), `raycast` mode `NONE|BLOCKS|ENTITIES|BLOCKS_AND_ENTITIES` + `ClipContext` fluid/blocker options, `color`, `renderer` (`InstancedRendererSetting`), `uvAnimation`, `lights`.

### 1.3 `TrailConfig` (`emitter/trail/TrailConfig.java`)

`duration`, `looping`, `startDelay`, `time` (trail history, default 20 ticks), `minVertexDistance`, `smoothInterpolation`, `uvMode` (`Stretch`), `widthOverTrail`, `colorOverTrail` (NumberFunctions), `renderer` (`InstancedRendererSetting`), `uvAnimation`, `lights`.

### 1.4 `AraTrailConfig` (`emitter/aratrail/AraTrailConfig.java`)

`duration`, `looping`, `section` (`TrailSection` — ribbon vertex profile), `space`/`alignment`/`sorting`/`timescale`/`textureMode` enums, `thickness`, `smoothness`, `corners`, `thicknessOverLength`/`thicknessOverTime`/`thicknessOverSegmentTime`, `colorOverLength/Time/SegmentTime`, `emit`, `initialThickness`/`initialColor`/`initialVelocity`/`timeInterval`/`minDistance`/`time`, `physicsSetting`, `renderer` (`InstancedRendererSetting`).

### 1.5 `ForceFieldObject` (`gameobject/forcefield/ForceFieldObject.java`)

`shape` enum `Sphere|Hemisphere|Cylinder|Box` + range (`startRange`, `endRange`), `direction` xyz, `gravity` + `gravityFocus`, `rotationSpeed` + `rotationAttraction` (vortex), `drag`, `rotationRandomness`, `runtimeBindings`. Applied per-particle via `apply(worldPos, worldVelocity, particleSize, dt, particle, multiplier)`; `FORCE_SCALE = 0.05f`. Catalog as an *affector*, not a visual primitive.

### 1.6 Sibling registries (what the "primitive" concept actually spans)

| Registry | Count | Names |
|---|---|---|
| `photon:material` | 7 | `missing`, `block_atlas`, `custom_shader`, `shader_graph`, `sprite`, `texture`, `ui_resource_material` |
| `photon:model_source` | 5 | `animated_gltf_model`, `gltf_model`, `json_model`, `obj_model`, `resource_mesh` |
| `photon:number_function` | 12 | `color`, `constant`, `curve`, `gradient`, `hdr_color`, `hdr_gradient`, `hdr_random_color`, `hdr_random_gradient`, `random_color`, `random_constant`, `random_curve`, `random_gradient` |
| `photon:shape` | 8 | `box`, `circle`, `cone`, `cylinder`, `dot`, `function`, `mesh`, `sphere` |
| `photon:animated_property` | 5 | `config`, `position`, `rotation`, `scale`, `speed` |
| `photon:timeline_track` | 8 | `activator`, `control`, `animation`, `signal`, `group`, `speed`, `audio`, `post_process` |

All populated by `@LDLRegisterClient` scanning in `PhotonRegistries.registerStaticInstances` — mirror the same scan to enumerate them exhaustively.

## 2. `.fx` file schema essentials

A `.fx` file is **gzip-compressed NBT** (`FX.SUFFIX = ".fx"`, `client/fx/FX.java`).

Root structure:

```
{ version: int?,          // format stamp written by editor export / FXPackExporter (FXProject.VERSION = 5); absent ⇒ treated as version 1
  fxData: {               // FX.serializeNBT → {"fxData": fxData.serializeNBT(provider)}
    fxObjects: [ {type: "<photon:fx_object id>", data: {...per-object persisted fields..., version stamped by FXObjectType.codec}} ],
    timeline: {tracks: [{type: "<photon:timeline_track id>", data: {...}}], markers: [{tick: double, name: string}]}   // only when non-empty
  }
}
```

- **`FX`** — the file-level unit: owns `FXData`, `createRuntime()` / `createRuntime(boolean deepCopy)` produce an `FXRuntime`. Also `createInternalRuntime()` (used for sub-emitters / nested instancing).
- **`FXData`** — the design-time object list (`List<IFXObject>`) + `Timeline`. `copy(boolean deepCopy)` is how a loaded FX becomes an independent runtime instance (runtime objects are deep-copied so the cached definition is never mutated).
- **`FXRuntime`** (`client/fx/FXRuntime.java`) — a live execution: `LinkedHashMap<UUID,IFXObject> objects` + a root `EmptyFXObject`. `emit(IEffectExecutor executor)` / `emit(executor, delay)` iterates all objects calling `fxObject.emit(effect[, position, rotation, scale])`, which inserts each FXObject into `Minecraft.getInstance().particleEngine` (or a `PhotonParticleManager`/`DummyWorld` ParticleTickHost in preview contexts). Liveness: `isFinished()` (all objects removed), `isAlive()`, `isValid()` (heartbeat — see §6), `destroy(force)`, `setRate(float)` timescale, `findObject(name)`.
- **Deserialization entry points**: `FXHelper.loadFX(ResourceLocation)` → `NbtIo.readCompressed` → `PhotonFXProjectDataFixer.applyFixes` when `version < FXProject.VERSION` (the fixer wraps it as `{fx:{...}}` — the project-file shape — before `fx.deserializeNBT`). `FXData.deserializeNBT` rebuilds objects via `IFXObject.CODEC` (`client/gameobject/IFXObject.java`): dispatch on the `photon:fx_object` registry name + `type.codec().fieldOf("data")`; each `FXObjectType.codec()` stamps its `version()` and `fixData` migrates per-type data.
- **FXHelper** (`client/fx/FXHelper.java`): `CACHE` is a `ConcurrentHashMap<ResourceLocation,FX>`; `getFX(id)` memoizes (id = `namespace:name`, where the on-disk path is `assets/<ns>/fx/<name>.fx`; a `fx/` prefix and `.fx` suffix are implied). `clearCache()` on resource reload. `listAllFX()` walks `resourceManager.listResources("fx", *.fx)` across all packs, returns a namespace-sorted unmodifiable `List<ResourceLocation>` held in a volatile `idCache`. Legacy embedded `resources` sections in a `.fx` only warn — see gotchas.

## 3. Spawn API

Canonical client-side spawn (mirrors `command/EntityEffectCommand.java` ~195-227 and `uitest/AnimatedGltfRenderScenario.startFox`):

```java
FX fx = FXHelper.getFX(ResourceLocation.fromNamespaceAndPath("photon", "my_fx"));
var executor = new BlockEffectExecutor(fx, level /*ClientLevel*/, blockPos);   // or:
var executor = new EntityEffectExecutor(fx, level, entity, EntityEffectExecutor.AutoRotate.FORWARD);
executor.setOffset(x, y, z);          // double overload or setOffset(Vector3f)
executor.setRotation(x, y, z);        // euler degrees; or setRotation(Quaternionf)
executor.setScale(x, y, z);           // or setScale(Vector3f)
executor.setDelay(ticks);             // whole-runtime start delay
executor.setForcedDeath(true|false);  // false (default): wait for natural particle death; true: hard kill on destruction
executor.setAllowMulti(bool);         // false (default): dedup — an identical live executor on the same entity/pos is retired/replaced
executor.setOnFinished(Consumer<FXRuntime>);
executor.start();                     // creates FXRuntime + emits all objects
```

Signatures: `IFXEffectExecutor` (`client/fx/IFXEffectExecutor.java`) + implementations `EntityEffectExecutor(FX, Level, Entity, AutoRotate)` and `BlockEffectExecutor(FX, Level, BlockPos)` (`client/fx/`).

- **`AutoRotate`**: `NONE | FORWARD | LOOK | XROT` — reorients the effect each frame from entity yaw/head in `updateFXObjectFrame`.
- **Auto-destroy**: static `CACHE` maps (`Map<Entity,List<EntityEffectExecutor>>`, `Map<BlockPos,List<BlockEffectExecutor>>`). An executor retires when its runtime is finished, the entity dies/is removed, the block changes, or the chunk unloads; `FXEffectExecutor` prunes dead runtimes so `!allowMulti` dedup only sees live ones. Both caches are dropped on `ParticleEngine.setLevel` (`core/mixins/ParticleEngineMixin`, `VanillaParticleHost.onWipe()`).
- **One-shot vs looped** is per-emitter, not per-FX: `config.looping` + `config.duration` (emitter sim duration). A non-looping emitter is killed at `ageF ≥ lifetime` (`Emitter.update`); a looping one never finishes by itself — the runtime stays alive until `runtime.destroy(force)` / forced death / executor retirement.
- Lower-level path: `fx.createRuntime()` → `runtime.emit(executor[, delay])`; an `IEffectExecutor` just needs `updateFXObjectTick(IFXObject)`, `updateFXObjectFrame(IFXObject,float)`, `onTimelineSignal`, `postEffectSink()` (defaults to `PostEffectStack.GLOBAL`). Server-side trigger path exists: `command/EntityEffectCommand|BlockEffectCommand|Remove*Command` send S2C `CustomPacketPayload`s (`photon:entity_effect_command` etc.) whose client handler builds the same executor + `start()`.

## 4. Asset inventory — `src/main/resources/assets/photon/`

| Kind | Count | Contents |
|---|---|---|
| lang | 2 | `en_us.json`, `zh_cn.json` |
| meshes | 6 `.obj` | `models/{capsule,cube,cylinder,plane,quad,sphere}.obj` — primitive geometry for mesh shapes/model render mode |
| textures | 34 files | `icon.png` (mod icon); `gui/icon/` 26 editor UI icons (beam, bloom, cull_box, draw_{both,shaded,wireframe}, force_field, fullscreengraph, lock, loop, marker, particle, photon_project, recording, shadergraph, shadergraph_function, shape_outline, timeline_end, trail, transport_{pause,play,step_back,step_forward,to_end,to_start}, unlock); `particle/` 7 = `circle,kila_tail,laser,ring,smoke,thaumcraft.png` + `thaumcraft.png.mcmeta` — **these 6 are the only user-facing particle textures shipped** |
| shaders | 89 files | see below |

Shader breakdown (`assets/photon/shaders/`):

- `core/` — 18 core-shader programs (`.json`): `hdr_particle`, `sprite_hdr_particle`, `pixel_hdr_particle` (the three HDR particle pipelines sharing `particle.vsh`), `bloom_add_pass`, `bloom_final_scatter_pass`, `bloom_scatter_pass`, `bright_pass`, `circle`, `down_sampling`, `up_sampling`, `inverse`, `iris_composite`, `mask`, `mask_union`, `separable_blur`, `unreal_composite`, `weight_mask_mix`, `weight_mix`. Of these, **only 11 are registered** at runtime: `PhotonShaders.registerShaders` registers `hdr_particle`, `sprite_hdr_particle`, `pixel_hdr_particle` (BLOCK format), `bright_pass`, `down_sampling`, `up_sampling`, `bloom_final_scatter_pass`, `weight_mix`, `weight_mask_mix`, `mask_union`, `iris_composite` (POSITION format) via `CoreShaderRegistrationCallback`; `bloom_add_pass`, `bloom_scatter_pass`, `separable_blur` are commented out; `circle`, `inverse`, `mask`, `unreal_composite` are dormant assets / consumed by postfx graphs rather than core registration. `catmull_rom.comp` is a compute shader loaded lazily by `PhotonShaders.init()` via `LDLibShaders` (gated on `supportComputeShader()`).
- `core/postfx/` — **23 composable screen-effect programs** (`.json` + `.fsh` each): `add_mix, blur_h, blur_v, bright, brightness_contrast, dof_composite, dot_screen, film, glitch, grayscale, hue_saturation, lens_distortion, mask_outline, outline, pixelate, posterize, radial_blur, rgb_shift, sepia, sharpen, show_mask, tint, vignette`. These are the raw shader programs; the *effects users see* are render graphs built **in code** (see below), which may reuse these programs — graph ids ≠ program ids.
- `include/` — 3 GLSL includes: `particle.glsl`, `particle_utils.glsl`, `soft_particle.glsl`.

**Not files**: builtin PostFX *effects* are code-built editor resources. `gui/editor/resource/RenderGraphResource.buildBuiltin` defines 22 render graphs (`invert_effect, grayscale, sepia, brightness_contrast, hue_saturation, vignette, rgb_shift, pixelate, dot_screen, film, glitch, gaussian_blur, outline, tint, sharpen, posterize, radial_blur, lens_distortion, bloom_effect, depth_of_field, show_mask, mask_outline`); `FullscreenShaderGraphResource.buildBuiltin` defines `passthrough` + `invert`. They are submitted per-frame with `PhotonPostFX.submit(IResourcePath, params, weight)` (builtin paths like `builtin:invert`) into `PostEffectStack.GLOBAL`, applied at `onLevelStageAfterParticles` / `onLevelRenderComplete` / `onFrameEnd`. No `.fx`, `.fxpack`, sound, font, or material files ship in `assets/photon/` — materials/shader graphs/curves are editor *resources* (`gui/editor/resource/*`), not asset files.

## 5. Programmatic FX creation → `.fx` on disk

Minimal path (exactly what `uitest/AnimatedGltfRenderScenario.startFox` does, then the editor export path):

```java
var emitter = new ParticleEmitter();            // or BeamEmitter/TrailEmitter/AraTrailEmitter/ForceFieldObject
emitter.config.setLooping(true);
emitter.config.setDuration(200);
emitter.config.setStartLifetime(NumberFunction.constant(200));
emitter.config.emission.getBursts().add(burst); // etc.
var fx = new FX();
fx.getFxData().objects().add(emitter);

// serialize + write — the same call the editor's "export fx" dialog uses (FXProject.showExportFxDialog):
var tag = fx.serializeNBT(Platform.getFrozenRegistry());
tag.putInt("version", FXProject.VERSION);       // stamp or datafixer treats it as v1
NbtIo.writeCompressed(tag, out.toPath());       // gzip
```

Class responsible: `FX.serializeNBT` → `{"fxData": ...}`; `IFXObject.CODEC` produces each `{type,data}` wrapper. The project editor (`gui/editor/FXProject.java`) is the canonical writer: `showExportFxDialog` writes via `NbtIo.writeCompressed` to `new File(LDLib2.getAssetsDir(), "photon/fx/<name>.fx")`.

**Where a `.fx` must sit** (`FXHelper` reads any `assets/<ns>/fx/*.fx` resource across all packs):

- a resource/mod jar: `assets/<ns>/fx/<name>.fx`;
- a user resource pack, same layout;
- **`<gameDir>/ldlib2/assets/<ns>/fx/<name>.fx`** — LDLib2 mounts `<gameDir>/ldlib2` as a hidden `CustomResourcePack` (`PackConfigMixin` in the ldlib2 jar); `LDLib2.getAssetsDir()` = `<gameDir>/ldlib2/assets`. This is where the editor exports — **the fast path for a test fixture in dev**.
- **`.fxpack` zips** (`client/fx/fxpack/FXPacks.java`): resource-pack-layout zips discovered at (a) `<gameDir>/photon/fxpacks/*.fxpack`, (b) `fxpacks/` at mod-jar root — folders are native-mounted, `.fxpack` files extracted to `<gameDir>/photon/fxpack_cache` content-addressed by FNV-1a-64. Mounted via `FXPacks.repositorySource()` appended to the client `PackRepository` by `core/mixins/PackRepositoryMixin` (fabric seam replacing Forge `AddPackFindersEvent`); hidden, built-in, BOTTOM priority; re-discovered every repository reload. `FXPacks.gc()` mark-sweeps unreferenced pack files.

## 6. Runtime measurement hooks

Everything needed for a per-tick sampling harness already exists as seam code:

- **Enumerate live particles**: `core/mixins/accessor/ParticleEngineAccessor.java` — `@Accessor Map<ParticleRenderType, Queue<Particle>> getParticles()`. Photon's own render types route FXObjects through custom buckets: `FXObject.NO_RENDER_RENDER_TYPE` (static `ParticleRenderType` with `RenderPassPipeline pipeline`), plus `ParticleQueueRenderType.TRANSLUCENT_QUEUE` / `OPAQUE_QUEUE` (emitters report `useTranslucentPipeline`/`getRenderType`). FX particles = the `Particle` instances in those queues + vanilla types other emitters add.
- **Per-emitter counts**: `IParticleEmitter.getParticleAmount()`; `ParticleEmitter.getParticles()` → `Map<PhotonFXRenderPass, Queue<IParticle>>` for per-pass/per-material breakdown. `Emitter.getAge()`/`getAgeF()`, `getLifetime()`, `getStartDelay()`, `isLooping()`, `getT(partialTicks)`, `getCullBox`, `getRenderBoundingBox()` (→ `FXHelper.INFINITE_AABB` when uncapped).
- **Runtime liveness**: `FXRuntime.isValid()` is heartbeat-based on `ParticleTickHost` (`client/fx/ParticleTickHost.java`): `tickCount()` advances once per engine tick, `generation()` bumps on mass-wipe. `VanillaParticleHost.INSTANCE` (`client/fx/VanillaParticleHost.java`) is fed by `ParticleEngineMixin` — `tick` HEAD (`onEngineTick`) and `setLevel` RETURN (`onWipe`). Root object records the heartbeat each tick ⇒ stale tickCount = engine no longer ticks this runtime.
- **Per-tick sampling points (client thread)**: `ClientTickEvents.END_CLIENT_TICK` (already used by `PhotonClientListeners`); deeper seams — `Emitter.onTickBegin()`/`updateTick(dt)` inside `FXObject.tick()` (delay countdown → timeline → `onUpdateTick` → `onTickBegin` → sub-stepped `updateTick`, `MAX_SUBSTEPS=16`, `dt ≤ 1`); `IEffectExecutor.updateFXObjectTick(IFXObject)` fires per-object per-tick on the executor (entity-anchored transforms etc.); `IParticleEmitter` per-particle `IParticle` data (position/lifetime) is reachable via `getParticles()` queues.
- **PostFX frame boundary**: `core/mixins/GameRendererMixin` → `PhotonPostFX.onFrameEnd()` each rendered frame; `LevelRendererMixin` → `onLevelStageAfterParticles`.

## 7. Photon-registered ParticleTypes

**None.** Exhaustive grep finds zero `ParticleType`/`BuiltInRegistries.PARTICLE`/`registerParticle` registrations in the module. FX objects are `Particle` subclasses instantiated directly and pushed into `ParticleEngine`'s queue by `IFXObject.emit` — they never go through the `ParticleType` + `ParticleProvider` mechanism, so they also never appear in `/particle` commands or `particles.json`. The "HDR" names (`hdr_particle`, `sprite_hdr_particle`, `pixel_hdr_particle`) are **core shaders**, not particle types; HDR color/gradient `number_function` entries are likewise functions, not types.

## 8. Client gametest / capture feasibility

- **fabric.mod.json entrypoints**: `main` = `Photon` (server/common init), `client` = `PhotonClientProxy` → `PhotonClientListeners.init()`. Fabric API `0.116.9+1.21.1` (gradle.properties).
- **Photon already has a client test harness**: `com.lowdragmc.photon.uitest` registers 12 `UIScenario`s against LDLib2's in-game UI test framework (`com.lowdragmc.lowdraglib2.uitest.*` — `UIScenario`, `ScenarioBuilder.step`, `TestContext`, `UITestRunner`), gated `RegistrationEnvironment.DEV_ONLY`. `TestContext` provides `mc()`, `player()`, `level()`, `screen()`, `server()`, `serverLevel()`, `serverPlayer()`, `onServer(...)` (server-thread exec), `state()` bag, `screenshot(name)` (writes `build/ldlib2-uitest/screenshots/<scenario>/<step>_<name>.png`), `input()` driver, `check`/`require`/`attach`. `uitest/ScreenshotCompare.java` = pixel-diff comparator (per-channel threshold + region scoping; region cropping matters — the editor stats box otherwise poisons diffs). Scenarios already spawn FX in-world via `new BlockEffectExecutor(fx, player.level(), pos)` + `setOffset` + `setAllowMulti` + `start()`, aim the camera via `player.setXRot/setYRot`, and pin animation clocks (`AnimatedGltfModelSource.pinClock`). This is the pattern to copy for the measurement harness.
- **fabric-api client gametest**: upstream `fabric-client-gametest-api-v1` (`FabricClientGameTest`/`ClientGameTestContext`) exists for 1.21.1 only as the standalone artifact `net.fabricmc.fabric-api:fabric-client-gametest-api-v1:4.3.1+1c21ffe5de` — it is **not** one of the modules fabric-api `0.116.9+1.21.1` pulls in (gradle cache shows only `fabric-gametest-api-v1`, server-side). Adding it is possible but the ldlib2 uitest framework already covers the need.
- **Level/renderer readiness**: `ctx.level()/player()` non-null inside a scenario; in the wild gate on `Minecraft.getInstance().level != null && player != null` and `particleEngine` live. Thread targeting: all FX ticking is on the client thread — enqueue via `Minecraft.getInstance().execute(...)` or hook `ClientTickEvents.END_CLIENT_TICK`; `ctx.onServer(...)` for server-side ops. Screenshots: `ctx.screenshot(name)` (harness) or vanilla `Screenshot.grab`/`Screenshot.takeScreenshot` (1.21.1 API) for ad-hoc; postfx frames are post-processed at `onFrameEnd` — capture after that point.
- **Camera control**: direct `player.setXRot/setYRot` (+`setPos`/`teleportTo` server-side for relocation) — proven in `AnimatedGltfRenderScenario.aimCamera`. For repeatable captures also fix `pos` deterministically and pin clocks where supported.
- **Debug/preview commands to reuse** (`client/ClientCommands.java`): `/photon_editor` (opens FXEditor via `ModularUIScreen`, 2-tick deferred open), `/photonfx test <effect> [weight]` / `photonfx clear` / `photonfx list` (PostFX submit/clear/enumerate), `/photon_client clear_particles` / `photon_client clear_client_fx_cache` / `photon_client convert` (Photon1→2 batch conversion via `client/fx/compat/FXCompat`), `/photon_iris status|probe|dump|overlay|mode`. Server-side `/photon ...` entity/block effect commands exist in `command/`.

## 9. NumberFunction / curve serialization

Every polymorphic config value uses the same `{type, data}` envelope: `NumberFunction.CODEC` (`emitter/data/number/NumberFunction.java`) dispatches on the `photon:number_function` registry name, wrapping `PersistedParser.createCodec(holder.value()).fieldOf("data")`. The identical pattern backs `IFXObject.CODEC`, `IMaterial`, `IShape`, `IModelSource`, timeline `Track`s, and `AnimatedProperty`s — a catalog extractor can use **one generic reader** for all of them.

Serialized shapes (`data` = @Persisted fields):

- `constant`: `{number: <numeric NBT>}`
- `random_constant`: `{a, b}` (two endpoints; `get` lerps `min(a,b)`→`max(a,b)`)
- `curve`: `{min, max, lower, upper, xAxis, yAxis, lockControlPoint, curves: <ECBCurves serialized>}` — `Curve` holds `ECBCurves` (editor bezier control points; evaluation `get(t, lerp)`)
- `random_curve`: two `curve`-shaped sub-functions (see `RandomCurve`)
- `color`: `{color: int ARGB}` (uniform tint)
- `gradient`: `{gradientColor: <GradientColor: rgbP [t,r,g,b] stops + aP [t,a] stops>}`
- `random_color` / `random_gradient`: paired color/gradient fields
- `hdr_color` / `hdr_gradient` / `hdr_random_*`: same shapes but values may exceed 1.0 (HDR intensity for bloom)
- `NumberFunction3` = **plain list of 3 `NumberFunction` envelopes** (`NumberFunction3.CODEC` is `NumberFunction.CODEC.listOf()` fixed to 3) — used for `startSize`, `startRotation`, position deltas, etc.

Extraction rules: read `type` then dispatch `data`; nested `NumberFunction`s recurse; `NumberFunction3` nests as a 3-element list. Non-function scalar fields (ints, strings, enums) serialize as their names directly in the parent `data` (`duration`, `looping`, `emissionMode`, `space`, …). Enum values serialize as their enum names.

## 10. FXPack export format — `client/fx/fxpack/FXPackExporter.java`

`exportInto(File fxpackFile, String namespace, String fxName, FX fx, HolderLookup.Provider)` appends **additively** into an existing `.fxpack` zip (or creates one). Layout:

```
assets/<namespace>/fx/<fxName>.fx              // gzip NBT, {version, fxData}; fx id = <packfile-basename-namespace>:<fxName>
assets/photon_fx/<kind>/<fnv1a64-hash>.<kind>.nbt   // content-addressed library resources, {type,data} wrapper
assets/photon/textures/... , models/*.glb, custom_shader .json/.vsh/.fsh …  // raw packable assets at their original resource paths
```

- Library serialization: every `IResource` reference embedded in the fx data is rewritten to a `FilePath` string `file(assets/photon_fx/<kind>/<hash>.<kind>.nbt)`; the resource body lands once per distinct content hash → shared resources stored once across fx.
- `isPackableAsset` covers `.png/.obj/.glb/.gltf` (textures & meshes) + `custom_shader` json/vsh/fsh; **raw assets ship under their original locations**, not content-addressed (or rather: packable assets go through `readPackableAsset` which copies them; assets already served by `vanilla`/`mod` packs are skipped — nothing to carry).
- `gc()` sweeps `photon_fx` entries no longer referenced; `json_model` sources **cannot be packed** (warned + skipped — gotcha); builtin paths skipped.
- `FXPacks.listFx/removeFx` support managing pack contents; a mounted pack can hold a file lock (Windows) — `isFileLocked` guards export.

## Gotchas — things that look catalogable but aren't / setup requirements / deprecated paths

- **`.fx` vs `.fxproj`**: `.fxproj` is the editor *project* file (`{meta:{version_num}, data:{fx:{...}}}` — `IProject` envelope incl. embedded editor resources); `.fx` is the runtime format (references only). `PhotonFXProjectDataFixer` converts `.fx` → project shape on load; don't hand the extractor `.fxproj` files expecting `.fx`.
- **Builtin resource paths**: `builtin:<name>` `IResourcePath`s (e.g. `builtin:invert`) resolve to *code-built* resources — they exist only when the editor resource registry is populated; they have no file form and are skipped by the exporter. `file(...)` and `resource(...)`/`pack(...)` FilePath forms need the ldlib2 editor `FileResourceProvider`/`PackFileResourceProvider` semantics, not plain `assets/` paths.
- **`json_model` model source can't be exported into an fxpack** (warning, skipped). `resource_mesh` (vanilla block/item model reference) resolves only against loaded model JSON, not a file.
- **PostFX effect ids ≠ postfx program files**: user-facing effects are the 22 code-built render graphs; `shaders/core/postfx/*.json` are implementation detail. A catalog should list *graph ids*, not program names (they overlap but differ: `gaussian_blur`, `bloom_effect`, `depth_of_field`, `invert_effect` exist only as graphs; `add_mix`, `blur_h/v`, `dof_composite`, `mask`, `inverse` exist only as programs).
- **Dormant shader assets**: `separable_blur`, `bloom_add_pass`, `bloom_scatter_pass` are registered *nowhere* (commented out in `PhotonShaders`); `circle`, `inverse`, `mask`, `unreal_composite` have no core registration — referenced from postfx graphs or dead.
- **Embedded resources in `.fx` are legacy**: `FXHelper.loadFX` warns on an old embedded `resources` section — data is ignored in favor of the fxpack/editor resource system. Photon1-era files live via `FXCompat` (`/photon_client convert`): put old files in `<gameDir>/ldlib2/assets/photon/fx_old/`, convert writes `photon/fx/` stamped `FXProject.VERSION`. Deprecated Photon1 object types do not map 1:1.
- **`maxParticles` interacts with `parallelUpdate`** (≥128 spawns the parallel path); **force_field does nothing unless sibling emitters enable `externalForces`**; looping emitters never `isFinished()` — a measurement harness must bound observation time itself; `startDelay` delays object start, executor `setDelay` delays whole runtime — different knobs.
- **fx id derivation**: id omits `fx/` and `.fx`; namespace = the *directory* namespace, and for fxpacks the namespace = **fxpack filename** (not a directory inside the zip). `getFX` caches forever until `clearCache()` — a stale-on-disk fixture requires `FXHelper.clearCache()` or a resource reload to be picked up.
- **Sub-emitter FX ids must resolve**: `SubEmittersSetting` looks up `FXHelper.getFX(fxLocation)` at particle-time — sub-FX must themselves be discoverable `assets/<ns>/fx/*.fx` (or in an fxpack), not just in-memory FX objects.
- **Registry scanning is annotation-driven**: `@LDLRegisterClient` fields are picked up reflectively by `PhotonRegistries.registerStaticInstances`; enumerating "types" from any source other than the registries (or the annotation grep) will miss entries.
- **`FXRuntime` emits into `particleEngine` on the client thread only**; in DummyWorld/preview contexts a `PhotonParticleManager` ParticleTickHost is used instead — measurement code must follow `IFXObject.emit`'s host dispatch, not assume `ParticleEngine`.
