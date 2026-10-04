# Vanilla Minecraft 1.21.1 — Visual Effects Inventory

**Source of truth:** loom-decompiled Mojang-mapped sources, `minecraft-1.21.1-loom.mappings.1_21_1.layered+hash.2198-v2` (common + clientOnly splits), from the Codex-Superheroes Gradle cache (`genSources`). Every name below is a real 1.21.1 mojmap class/member; nothing is recalled from memory. Packages are split: `net.minecraft.core/world/server/...` live in *common*, `net.minecraft.client.*` in *clientOnly*.

Key 1.21.1 correctness notes up front:

- `TrailParticleOption`, `EntityEffect`, `SpellParticleOption` **do not exist** in 1.21.1 (they arrived in 1.21.2/1.21.4+). `SpellParticle` exists but is a *client particle implementation class*, not an options type.
- `/particle` options syntax is **inline NBT**, not the pre-1.20.5 positional grammar: `minecraft:dust{color:[1.0,0.0,0.0],scale:2.0}`.
- The registry count is **109** particle types (98 `SimpleParticleType` + 11 parameterized).

---

## 1. `ParticleType` enumeration — all 109 registrations

Registered in `net.minecraft.core.particles.ParticleTypes` into `BuiltInRegistries.PARTICLE_TYPE` (all ids are `minecraft:<id>`). Column **lmt** is the `overrideLimiter` flag passed to `register(id, flag)`: when `true`, the client force-renders the particle regardless of the Particles video setting and the 32-block camera cull (`ParticleType#getOverrideLimiter`).

### Parameterized types (11 registrations, 8 distinct option classes)

| id | option class | lmt |
|---|---|---|
| `block` | `BlockParticleOption` | f |
| `block_marker` | `BlockParticleOption` | **t** |
| `falling_dust` | `BlockParticleOption` | f |
| `dust_pillar` | `BlockParticleOption` | f |
| `dust` | `DustParticleOptions` | f |
| `dust_color_transition` | `DustColorTransitionOptions` | f |
| `entity_effect` | `ColorParticleOption` | f |
| `item` | `ItemParticleOption` | f |
| `sculk_charge` | `SculkChargeParticleOptions` | **t** |
| `vibration` | `VibrationParticleOption` | **t** |
| `shriek` | `ShriekParticleOption` | f |

### SimpleParticleType registrations (98)

`angry_villager`, `bubble`, `cloud`, `crit`, `damage_indicator` **t**, `dragon_breath`, `dripping_lava`, `falling_lava`, `landing_lava`, `dripping_water`, `falling_water`, `effect`, `elder_guardian` **t**, `enchanted_hit`, `enchant`, `end_rod`, `explosion_emitter` **t**, `explosion` **t**, `gust` **t**, `small_gust`, `gust_emitter_large` **t**, `gust_emitter_small` **t**, `sonic_boom` **t**, `firework`, `fishing`, `flame`, `infested`, `cherry_leaves`, `sculk_soul`, `sculk_charge_pop` **t**, `soul_fire_flame`, `soul`, `flash`, `happy_villager`, `composter`, `heart`, `instant_effect`, `item_slime`, `item_cobweb`, `item_snowball`, `large_smoke`, `lava`, `mycelium`, `note`, `poof` **t**, `portal`, `rain`, `smoke`, `white_smoke`, `sneeze`, `spit` **t**, `squid_ink` **t**, `sweep_attack` **t**, `totem_of_undying`, `underwater`, `splash`, `witch`, `bubble_pop`, `current_down`, `bubble_column_up`, `nautilus`, `dolphin`, `campfire_cosy_smoke` **t**, `campfire_signal_smoke` **t**, `dripping_honey`, `falling_honey`, `landing_honey`, `falling_nectar`, `falling_spore_blossom`, `ash`, `crimson_spore`, `warped_spore`, `spore_blossom_air`, `dripping_obsidian_tear`, `falling_obsidian_tear`, `landing_obsidian_tear`, `reverse_portal`, `white_ash`, `small_flame`, `snowflake`, `dripping_dripstone_lava`, `falling_dripstone_lava`, `dripping_dripstone_water`, `falling_dripstone_water`, `glow_squid_ink` **t**, `glow` **t**, `wax_on` **t**, `wax_off` **t**, `electric_spark` **t**, `scrape` **t**, `egg_crack`, `dust_plume`, `trial_spawner_detection` **t**, `trial_spawner_detection_ominous` **t**, `vault_connection` **t**, `ominous_spawning` **t**, `raid_omen`, `trial_omen`

**t** = `overrideLimiter` true (25 of 98 simple types; 3 parameterized — `block_marker`, `sculk_charge`, `vibration`).

### Parameterized option schemas (verified from each class's `CODEC`/`STREAM_CODEC`)

| Options class | NBT/codec fields | Notes |
|---|---|---|
| `BlockParticleOption` | `block_state`: `BlockState.CODEC` **or** bare block id (`Codec.withAlternative(BlockState.CODEC, BLOCK.byNameCodec(), Block::defaultBlockState)`) | bare id resolves to default blockstate; network = `Block.BLOCK_STATE_REGISTRY` id |
| `DustParticleOptions` | `color`: `Vector3f` (floats 0–1 RGB), `scale`: float | extends `ScalableParticleOptionsBase`: codec **validates** scale ∈ [0.01, 4.0] (command parse error); ctor additionally `Mth.clamp`s, so direct API use can't exceed the range. Preset `REDSTONE` = (1.0,0.0,0.0)×1.0 |
| `DustColorTransitionOptions` | `from_color`, `to_color`: `Vector3f`; `scale`: float | same scale validation/clamp. Preset `SCULK_TO_REDSTONE` = sculk teal (0.224,0.843,0.878; RGB24 3790560) → redstone red |
| `ColorParticleOption` | `color`: ARGB int (`ExtraCodecs.ARGB_COLOR_CODEC` — also accepts `[r,g,b,a]` float list) | ctor private; use `ColorParticleOption.create(type, int)` / `create(type, r, g, b)`; getters normalize /255. `MobEffect` uses alpha 255, or `AMBIENT_ALPHA` = ⌊38.25⌋ = 38 for ambient |
| `ItemParticleOption` | `item`: `ItemStack` (`SINGLE_ITEM_CODEC` ∥ `ITEM_NON_AIR_CODEC` ∥ bare item id → `new ItemStack`) | throws `IllegalArgumentException` on empty stack |
| `SculkChargeParticleOptions` | `roll`: float (record component) | rotation roll; `π` = downward-facing charge (used by sculk spread), `0` = up |
| `ShriekParticleOption` | `delay`: int | ticks of delay before the particle plays (shrieker uses `i*5` per ring) |
| `VibrationParticleOption` | `destination`: `PositionSource` (`{type:"minecraft:block",pos:[x,y,z]}` ∥ `entity`), `arrival_in_ticks`: int | **the codec rejects `EntityPositionSource`** ("Entity position sources are not allowed") — `/particle` can't target entities. The `STREAM_CODEC` does *not* validate, so server `sendParticles` legitimately sends entity destinations (Warden uses `EntityPositionSource(this, eyeHeight)`). Particle moves spawn→destination over `arrival_in_ticks` |

Base classes: `ParticleType<T extends ParticleOptions>` (abstract; `codec()`, `streamCodec()`, `getOverrideLimiter()`), `ParticleOptions` (`getType()`), `SimpleParticleType` (`extends ParticleType<SimpleParticleType> implements ParticleOptions`, codec=unit). Dispatch: `ParticleTypes.CODEC` dispatches on `"type"` key; `ParticleTypes.STREAM_CODEC` dispatches on registry id (`ByteBufCodecs.registry(Registries.PARTICLE_TYPE)`).

`ParticleGroup`: only `ParticleGroup.SPORE_BLOSSOM` (limit 1000) — per-group live-count cap in `ParticleEngine`.

---

## 2. Spawn APIs (exact 1.21.1 signatures)

### Server → clients

```java
// ServerLevel.java
public <T extends ParticleOptions> int sendParticles(
    T particleOptions, double x, double y, double z, int count,
    double dx, double dy, double dz, double maxSpeed)          // broadcasts to all players in level

public <T extends ParticleOptions> boolean sendParticles(
    ServerPlayer player, T particleOptions, boolean force, double x, double y, double z,
    int count, double dx, double dy, double dz, double maxSpeed)

public final boolean sendParticles(ServerPlayer player, boolean force,
    double x, double y, double z, Packet<?> packet)            // gate: player.blockPosition()
                                                             // .closerToCenterThan(xyz, force?512:32)
```

Sends `ClientboundLevelParticlesPacket` — fields: `ParticleOptions particle`, `boolean overrideLimiter`, `double x,y,z`, `float xDist,yDist,zDist` ("delta"), `float maxSpeed`, `int count`. The same `force` flag (a) widens the server send radius 32→512 blocks and (b) becomes the packet's `overrideLimiter`.

**Client decode** (`ClientPacketListener#handleParticleEvent`): `count==0` → one particle at exact pos, velocity = `maxSpeed × (xDist,yDist,zDist)`; `count>0` → `count` particles at `pos + gaussian×(xDist,yDist,zDist)`, velocity `gaussian×maxSpeed` per axis; each goes to `level.addParticle(options, isOverrideLimiter(), ...)`.

### Client side (single-player / packet handling)

```java
// ClientLevel.java → LevelRenderer#addParticle
public void addParticle(ParticleOptions o, double x, double y, double z, double xd, double yd, double zd)
    // force = o.getType().getOverrideLimiter()
public void addParticle(ParticleOptions o, boolean force, double x, ..., double zd)
    // force = o.getType().getOverrideLimiter() || force
public void addAlwaysVisibleParticle(ParticleOptions o, double x, ..., double zd)
    // LevelRenderer.addParticle(o, false, true, ...) — "alwaysVisible"
public void addAlwaysVisibleParticle(ParticleOptions o, boolean force, double x, ..., double zd)
    // force = o.getType().getOverrideLimiter() || force, alwaysVisible = true
```

`LevelRenderer#addParticleInternal(options, force, alwaysVisible, x,y,z, xd,yd,zd)` (private): `force` → straight to `particleEngine.createParticle`; else camera `distanceToSqr > 1024` → null; `ParticleStatus.MINIMAL` → null. `alwaysVisible` only softens the status roll in `calculateParticleLevel` (MINIMAL→DECREASED w.p. 1/10; DECREASED→MINIMAL w.p. 1/3) — it does **not** bypass the 32-block cull.

```java
// ParticleEngine.java
public @Nullable Particle createParticle(ParticleOptions o, double x, double y, double z, double xd, double yd, double zd)
    // → makeParticle → providers.get(PARTICLE_TYPE.getId(type)) → provider.createParticle → add()
public void add(Particle particle)                    // universal enqueue → particlesToAdd (group cap)
public void createTrackingEmitter(Entity e, ParticleOptions o)           // lifeTime = 3
public void createTrackingEmitter(Entity e, ParticleOptions o, int lifeTime) // totem uses 30
public void destroy(BlockPos, BlockState)             // terrain particle burst (block break)
public void crack(BlockPos, Direction)                // crack-dig particles
public String countParticles()                        // total live count (as String)
```

```java
// LevelAccessor / Level / ServerLevel / ClientLevel
void levelEvent(@Nullable Player, int type, BlockPos pos, int data);      // LevelAccessor, abstract
default void levelEvent(int type, BlockPos pos, int data)                 // → (null, ...)
// ServerLevel: broadcast ClientboundLevelEventPacket(type,pos,data,global=false) within 64 blocks of pos
// Level#globalLevelEvent → ClientboundLevelEventPacket(..., global=true) when gamerule global_sound_events
// ClientLevel#levelEvent → levelRenderer.levelEvent(type,pos,data) — the big switch (§3)
// ClientLevel#globalLevelEvent → LevelRenderer#globalLevelEvent — sound re-aimed 2 blocks from camera
// Level#destroyBlock → levelEvent(2001, pos, Block.getId(state)) — canonical break path
```

### `/particle` command grammar (1.21.1)

```
/particle <name> [<pos> [<delta> <speed> <count> [force|normal [<viewers>]]]]
```

- `name` = `ParticleArgument` — `ResourceLocation` + optional `{nbt}` parsed by `particleType.codec().codec()` against `NbtOps` (empty tag allowed; `SimpleParticleType` codec is `MapCodec.unit`). Examples:
  - `particle minecraft:dust{color:[1.0,0.0,0.0],scale:2.0}`
  - `particle minecraft:dust_color_transition{from_color:[0.22,0.84,0.88],to_color:[1.0,0.0,0.0],scale:1.5}`
  - `particle minecraft:block{block_state:{Name:"minecraft:stone"}}` (or `{block_state:"minecraft:stone"}`)
  - `particle minecraft:item{item:{id:"minecraft:diamond",count:1}}` (or `{item:"minecraft:diamond"}`)
  - `particle minecraft:entity_effect{color:-52429}` or `{color:[1.0,0.4,0.0,1.0]}` (list order r,g,b,a)
  - `particle minecraft:sculk_charge{roll:3.14159265}`, `particle minecraft:shriek{delay:20}`
  - `particle minecraft:vibration{destination:{type:"minecraft:block",pos:[0,64,0]},arrival_in_ticks:40}` — `type:"entity"` destination is rejected by the command codec
- `force` → packet `overrideLimiter` + 512-block radius (vs `normal` = 32).

---

## 3. `LevelEvent` enumeration — all 82 constants

`net.minecraft.world.level.block.LevelEvent`. Handled client-side in `LevelRenderer#levelEvent(int, BlockPos, int)` (local) or `LevelRenderer#globalLevelEvent` (globals). **Every constant has a client handler — none are dead.**

### Visual events — produce particles/visuals (39)

| id | name | data | client effect |
|---|---|---|---|
| 1051 | `SOUND_WIND_CHARGE_SHOOT` | direction3D | `WIND_CHARGE_THROW` sound + **falls through to 2010** → 10 `WHITE_SMOKE` shot toward dir |
| 1500 | `COMPOSTER_FILL` | >0 = success sound | sound + 10× `COMPOSTER` |
| 1501 | `LAVA_FIZZ` | — | `LAVA_EXTINGUISH` + 8× `LARGE_SMOKE` |
| 1502 | `REDSTONE_TORCH_BURNOUT` | — | sound + 5× `SMOKE` |
| 1503 | `END_PORTAL_FRAME_FILL` | — | sound + 16× `SMOKE` |
| 1504 | `DRIPSTONE_DRIP` | — | `PointedDripstoneBlock.spawnDripParticle` — 1 drip particle (visual only) |
| 1505 | `PARTICLES_AND_SOUND_PLANT_GROWTH` | count | `BONE_MEAL_USE` + `HAPPY_VILLAGER` ×count (×3 for NEIGHBOR_SPREADER/water) |
| 2000 | `PARTICLES_SHOOT_SMOKE` | `Direction` 3D value | 10× `SMOKE` toward face (visual only) |
| 2001 | `PARTICLES_DESTROY_BLOCK` | block state id | block break sound + `ParticleEngine.destroy` terrain burst |
| 2002 | `PARTICLES_SPELL_POTION_SPLASH` | packed RGB | 8× `ITEM`(splash_potion) + 100× `EFFECT` colored `(data>>16&FF, >>8&FF, &FF)/255` + splash sound |
| 2003 | `PARTICLES_EYE_OF_ENDER_DEATH` | — | 8× `ITEM`(ender_eye) + 2×20 `PORTAL` ring (visual only) |
| 2004 | `PARTICLES_MOBBLOCK_SPAWN` | — | 20× `SMOKE` + 20× `FLAME` (visual only) |
| 2006 | `PARTICLES_DRAGON_FIREBALL_SPLASH` | 1=+sound | 200× `DRAGON_BREATH` (+`DRAGON_FIREBALL_EXPLODE` if data==1; `DragonFireball` sends `isSilent?-1:1`) |
| 2007 | `PARTICLES_INSTANT_POTION_SPLASH` | packed RGB | as 2002 but `INSTANT_EFFECT` |
| 2008 | `PARTICLES_DRAGON_BLOCK_BREAK` | — | 1× `EXPLOSION` (visual only) |
| 2009 | `PARTICLES_WATER_EVAPORATING` | — | 8× `CLOUD` (visual only) |
| 2010 | `PARTICLES_SHOOT_WHITE_SMOKE` | `Direction` 3D value | 10× `WHITE_SMOKE` (visual only) |
| 2011 | `PARTICLES_BEE_GROWTH` | count | `HAPPY_VILLAGER` ×count in block (visual only) |
| 2012 | `PARTICLES_TURTLE_EGG_PLACEMENT` | count | `HAPPY_VILLAGER` ×count (visual only) |
| 2013 | `PARTICLES_SMASH_ATTACK` | count | `spawnSmashAttackParticles` — `DUST_PILLAR`(blockstate at pos) ring + center burst |
| 3000 | `ANIMATION_END_GATEWAY_SPAWN` | — | `EXPLOSION_EMITTER` (force) + `END_GATEWAY_SPAWN` sound |
| 3002 | `PARTICLES_ELECTRIC_SPARK` | `Axis` idx (0-2) | `ELECTRIC_SPARK` 10–19 along axis, else 3–5 per face |
| 3003 | `PARTICLES_AND_SOUND_WAX_ON` | — | `WAX_ON` 3–5/face + `HONEYCOMB_WAX_ON` |
| 3004 | `PARTICLES_WAX_OFF` | — | `WAX_OFF` 3–5/face (visual only) |
| 3005 | `PARTICLES_SCRAPE` | — | `SCRAPE` 3–5/face (visual only) |
| 3006 | `PARTICLES_SCULK_CHARGE` | `(charge_lvl<<6)\|packed_faces` | `data>>6` charge level → per-face `SculkChargeParticleOptions(π|0)` streaks + maybe `SCULK_BLOCK_CHARGE` sound; `data==0` → `SCULK_CHARGE_POP` burst (20/40) + sound |
| 3007 | `PARTICLES_SCULK_SHRIEK` | — | 10× `shriek(delay=i*5)` at `y+TOP_Y` + `SCULK_SHRIEKER_SHRIEK` unless waterlogged |
| 3008 | `PARTICLES_AND_SOUND_BRUSH_BLOCK_COMPLETE` | block state id | brush-complete sound + `addDestroyBlockEffect` |
| 3009 | `PARTICLES_EGG_CRACK` | — | `EGG_CRACK` 3–6/face (visual only) |
| 3011 | `PARTICLES_TRIAL_SPAWNER_SPAWN` | `FlameParticle` idx | 20× (`SMOKE` + `FLAME`(0)/`SOUL_FIRE_FLAME`(1)) |
| 3012 | `PARTICLES_TRIAL_SPAWNER_SPAWN_MOB_AT` | `FlameParticle` idx | `TRIAL_SPAWNER_SPAWN_MOB` + same particles |
| 3013 | `PARTICLES_TRIAL_SPAWNER_DETECT_PLAYER` | player count | `DETECT_PLAYER` sound + `TRIAL_SPAWNER_DETECTED_PLAYER` ×(30+min(data,10)×5) |
| 3014 | `ANIMATION_TRIAL_SPAWNER_EJECT_ITEM` | — | `EJECT_ITEM` sound + 20×(`SMALL_FLAME`+`SMOKE`) |
| 3015 | `ANIMATION_VAULT_ACTIVATE` | 0→`SMALL_FLAME`,≠0→`SOUL_FIRE_FLAME` | vault `Client.emitActivationParticles` + `VAULT_ACTIVATE` |
| 3016 | `ANIMATION_VAULT_DEACTIVATE` | same | `emitDeactivationParticles` + `VAULT_DEACTIVATE` |
| 3017 | `ANIMATION_VAULT_EJECT_ITEM` | — | eject particles only (visual only) |
| 3018 | `ANIMATION_SPAWN_COBWEB` | — | 10× `POOF` + `COBWEB_PLACE` |
| 3019 | `PARTICLES_TRIAL_SPAWNER_DETECT_PLAYER_OMINOUS` | player count | detect sound + `..._DETECTED_PLAYER_OMINOUS` ×count |
| 3020 | `PARTICLES_TRIAL_SPAWNER_BECOME_OMINOUS` | 0→vol 0.3 | `OMINOUS_ACTIVATE` + detected-ominous + 20×(`TRIAL_OMEN`+`SOUL_FIRE_FLAME`) |
| 3021 | `PARTICLES_TRIAL_SPAWNER_SPAWN_ITEM` | `FlameParticle` idx | `SPAWN_ITEM` sound + spawn particles |

### Sound-only (39 local + 3 global = 42)

Local (39): 1000 dispenser, 1001 dispenser fail, 1002 projectile launch, 1004 firework shoot, 1009 extinguish fire (data 0/1 variant), 1010 jukebox play (**data = `JukeboxSong` registry holder id**), 1011 jukebox stop, 1015 ghast warn, 1016 ghast fireball, 1017 dragon fireball, 1018 blaze fireball, 1019 zombie wooden door, 1020 zombie iron door, 1021 zombie door crash, 1022 wither block break, 1024 wither shoot, 1025 bat liftoff, 1026 zombie infected, 1027 zombie converted, 1029 anvil broken, 1030 anvil used, 1031 anvil land, 1032 portal travel (local ambience), 1033 chorus grow, 1034 chorus death, 1035 brewing stand, 1039 phantom bite, 1040 zombie→drowned, 1041 husk→zombie, 1042 grindstone, 1043 page turn, 1044 smithing table, 1045 dripstone land, 1046 drip lava cauldron, 1047 drip water cauldron, 1048 skeleton→stray, 1049 crafter craft, 1050 crafter fail, 3001 dragon summon roar.

Global (3, `globalEvent=true`, sound re-aimed 2 blocks from camera toward event pos): 1023 `SOUND_WITHER_BOSS_SPAWN`, 1028 `SOUND_DRAGON_DEATH`, 1038 `SOUND_END_PORTAL_SPAWN`. If a server fires these via plain `levelEvent` (not `globalLevelEvent`), the client does nothing.

---

## 4. Parameterized-particle preview variants

| type | variant | spawn form |
|---|---|---|
| `dust` | redstone stock / red large / green small / black med | `{color:[1,0,0],scale:1}` / `{color:[1,0,0],scale:4.0}` / `{color:[0,1,0.13],scale:0.4}` / `{color:[0,0,0],scale:2.0}` — scale hard cap [0.01,4.0] |
| `dust_color_transition` | sculk→redstone (vanilla) / white→black / teal→magenta | `{from_color:[0.22,0.84,0.88],to_color:[1,0,0],scale:1}` etc. |
| `block` | stone / glass (translucent tex) / red_wool | `{block_state:"minecraft:stone"}` etc.; same option reused for `falling_dust`, `block_marker`, `dust_pillar` previews |
| `item` | diamond / totem / honey bottle | `{item:{id:"minecraft:diamond",count:1}}` |
| `entity_effect` | opaque red / ambient-alpha green / RGBA list | `{color:-65536}` / `create(ENTITY_EFFECT, ARGB(38,r,g,b))` / `{color:[0.2,0.8,1.0,1.0]}` |
| `sculk_charge` | upward roll / downward (π) / skewed | `{roll:0.0}` / `{roll:3.14159265}` / `{roll:1.2}` |
| `shriek` | instant / staggered rings | `{delay:0}` / `{delay:10}` / `{delay:25}` |
| `vibration` | block destination 40t / slow 80t / fast 10t | `{destination:{type:"minecraft:block",pos:[x,y,z]},arrival_in_ticks:N}` — server API can also pass `EntityPositionSource` for warden-style target-seeking |

---

## 5. Composite / multi-particle vanilla effects (all real in 1.21.1)

| effect | trigger | what happens |
|---|---|---|
| Totem resurrection | `broadcastEntityEvent(entity, 35)` → `ClientPacketListener` | `createTrackingEmitter(entity, TOTEM_OF_UNDYING, 30)` (16/tick around entity) + `TOTEM_USE` + `gameRenderer.displayItemActivation` overlay |
| Warden sonic boom | `SonicBoom` behavior → `sendParticles(SONIC_BOOM, …, 1, 0,0,0, 0)` per step | `SONIC_BOOM` row along ray + `WARDEN_SONIC_BOOM` |
| Vibration travel | `VibrationSystem` listener → `sendParticles(new VibrationParticleOption(src, travelTicks),…)` | directed vibration streak (entity or block destination) |
| Sculk catalyst bloom | `SculkCatalystBlockEntity.bloom` → `sendParticles(SCULK_SOUL, …, 2, .2,0,.2, 0)`; spread via `SculkSpreader` → `levelEvent(3006, pos, (lvl<<6)\|faces)` | sculk souls + charge streaks / `SCULK_CHARGE_POP` bursts |
| Sculk shrieker | `levelEvent(3007, pos, 0)` | staggered `shriek` rings + shriek |
| Dragon fireball splash + breath area | `DragonFireball` → `levelEvent(2006, pos, isSilent?-1:1)` + spawns `AreaEffectCloud` (synced `DATA_PARTICLE=DRAGON_BREATH`, ambient via `addAlwaysVisibleParticle`) | 200-burst + lingering cloud field |
| End gateway spawn | `globalLevelEvent`/event 3000 | `EXPLOSION_EMITTER` + gateway sound (beam itself is `TheEndGatewayBlockEntity` renderer, not particles) |
| Trial spawner suite | `levelEvent` 3011/3012/3013/3014/3019/3020/3021 | smoke+flame ring, detect spiral, ominous transform (`TRIAL_OMEN`+`SOUL_FIRE_FLAME`), eject item |
| Vault | `levelEvent` 3015–3017 | flame/soul-fire activation sweep, eject burst |
| Wind charge / breeze burst | `AbstractWindCharge.explode` → `ClientboundExplodePacket(small=GUST_EMITTER_SMALL, large=GUST_EMITTER_LARGE)` + `levelEvent(1051/2010)` white smoke | emitter-type gust particles + directional smoke |
| Explosion (generic) | `ClientboundExplodePacket` → client `Explosion.finalizeExplosion(true)` | `EXPLOSION`/`EXPLOSION_EMITTER` (packet carries both `ParticleOptions` — data-driven since 1.21) |
| Elder guardian curse | `ClientboundGameEventPacket.GUARDIAN_ELDER_EFFECT` | `ELDER_GUARDIAN` particle ghost at player + curse sound (when value==1) |
| Firework explosion | `Level.createFireworks` → client `ClientLevel.createFireworks` | `particleEngine.add(new FireworkParticles.Starter(...))` composite burst (empty list → `POOF` fallback) |
| Potion splash | `levelEvent` 2002/2007 | 100 colored effect swirls + 8 item shards + splash |
| Block break | `levelEvent` 2001 (`destroyBlock`) | `ParticleEngine.destroy` terrain burst + break sound |
| Ender-eye death | `levelEvent` 2003 | item shards + 40-strong `PORTAL` ring |
| Entity portal/teleport shimmer | `broadcastEntityEvent(entity, 46)` | 128 `PORTAL` particles lerped along motion |
| Ominous item spawner | `OminousItemSpawner.addParticles` (entity client tick) | `OMINOUS_SPAWNING` stream |
| Mob-effect ambience | `MobEffect.particleFactory` → `ENTITY_EFFECT`/`SpellParticle` types (`raid_omen`, `trial_omen`, …) | per-tick ambient swirls around entity |

Sound-only composites worth noting: copper bulb toggle (`serverLevel.playSound` — `COPPER_BULB_TURN_ON/OFF`; the lit face is a blockstate/emissive, *not* particles).

---

## 6. Measurement accessibility — `ParticleEngine`/`Particle` internals (mojmap 1.21.1)

Entry object: `Minecraft#getInstance().particleEngine` — `public final ParticleEngine particleEngine` (Minecraft.java:281).

**Fields** (`ParticleEngine`):
- `private final Map<ParticleRenderType, Queue<Particle>> particles` — `IdentityHashMap`; queues are `EvictingQueue.create(16384)` per render type (`MAX_PARTICLES_PER_LAYER = 16384`). New arrivals buffer into `private final Queue<Particle> particlesToAdd` and are distributed in `tick()`.
- `private final Queue<TrackingEmitter> trackingEmitters` — entity-bound emitters (`createTrackingEmitter` — **bypasses `add()`**, observe separately).
- `private final Int2ObjectMap<ParticleProvider<?>> providers` — keyed by `BuiltInRegistries.PARTICLE_TYPE.getId(type)`.
- `private final Object2IntOpenHashMap<ParticleGroup> trackedParticleCounts` — per-group caps (only `SPORE_BLOSSOM`, 1000).
- `RENDER_ORDER` = TERRAIN_SHEET, PARTICLE_SHEET_OPAQUE, PARTICLE_SHEET_LIT, PARTICLE_SHEET_TRANSLUCENT, CUSTOM (NO_RENDER excluded).

**Public accessor:** `countParticles()` → `String` of total live count (used by the F3 counter). No int getter — mixin/accessor needed for structured reads.

**Mixin points for a capture harness:**
- `ParticleEngine#add(Particle)` — *universal* enqueue (HEAD inject sees every live particle: `createParticle`, terrain `destroy`/`crack`, `FireworkParticles.Starter` all funnel here). Best single hook.
- `ParticleEngine#createParticle(ParticleOptions, x,y,z, xd,yd,zd)` — pre-construction hook that still sees the `ParticleOptions` (type + params) before it dissolves into a `Particle`; ideal for attribute capture (id, codec-encoded params, requested pos/vel).
- `ParticleEngine#tickParticleList` / `tickParticle` — per-tick lifecycle (private; inject to observe age-out).
- `ParticleEngine#createTrackingEmitter` — emitter effects (totem).
- `ClientLevel#levelEvent` / `LevelRenderer#levelEvent` — catch composite triggers (the `type`/`data` ints) before they fan out to particles.

**`Particle` fields** (all `protected`/`private` on `net.minecraft.client.particle.Particle`): `x,y,z` (current), `xo,yo,zo` (prev), `xd,yd,zd` (velocity), `bb` (`AABB`, `getBoundingBox()`), `bbWidth/bbHeight`, `age`, `lifetime` (`getLifetime()`), `gravity`, `friction`, `rCol/gCol/bCol`, `alpha`, `roll/oRoll`, `onGround`, `hasPhysics`, `removed` (`isAlive()`), `speedUpWhenYMotionIsBlocked`; `getRenderType()` → `ParticleRenderType`, `getParticleGroup()` → `Optional<ParticleGroup>`. Useful helpers: `setPower`, `scale`, `setColor`, `setParticleSpeed`.

---

## Structured summary

- **109** registered particle types; **11 parameterized** (7 distinct options classes: `BlockParticleOption`, `DustParticleOptions`, `DustColorTransitionOptions`, `ColorParticleOption`, `ItemParticleOption`, `SculkChargeParticleOptions`, `VibrationParticleOption`, `ShriekParticleOption` — that is 8 classes across 11 registrations).
- **82** `LevelEvent` constants: **39 visual**, 39 local sound-only, 3 global-sound (1023/1028/1038), 1 hybrid (1051, falls through to 2010).
- Best capture-harness entry points: **(1)** `ParticleEngine#add` (every live particle), **(2)** `ParticleEngine#createParticle` (typed options + pos/vel pre-dissolve), **(3)** `ServerLevel#sendParticles` / client `levelEvent` handlers (composite semantics before fan-out).
