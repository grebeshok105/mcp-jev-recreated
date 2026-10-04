package io.jevlab.probe.capture;

import com.google.gson.JsonObject;
import com.lowdragmc.photon.client.fx.BlockEffectExecutor;
import com.lowdragmc.photon.client.fx.FX;
import com.lowdragmc.photon.client.fx.FXHelper;
import java.util.List;
import java.util.Random;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.Vec3;

/** Spawns one capture subject per shot kind. Returned handle tears the subject down. */
public final class Spawner {
    private static final Random RANDOM = new Random(0xC0FFEE);

    private Spawner() {}

    /** Most recent quasar manager+emitter pair, exposed for per-tick diagnostics. */
    public static volatile Object LAST_QUASAR_MANAGER = null;
    public static volatile Object LAST_QUASAR_EMITTER = null;

    public interface SpawnHandle {
        SpawnHandle NONE = () -> {};
        void stop();
    }

    public static SpawnHandle spawn(
            CapturePlan.Shot shot,
            ClientLevel level,
            Vec3 at,
            net.minecraft.server.MinecraftServer server,
            List<String> diagnostics) {
        return switch (shot.kind) {
            case "particle" -> spawnParticle(shot, level, at, diagnostics);
            case "level_event" -> spawnLevelEvent(shot, at, server, diagnostics);
            case "fx" -> spawnFx(shot, level, at, diagnostics);
            case "quasar_emitter" -> spawnQuasar(shot, at, diagnostics);
            default -> {
                diagnostics.add("spawner: unknown kind '" + shot.kind + "' for " + shot.id);
                yield SpawnHandle.NONE;
            }
        };
    }

    private static SpawnHandle spawnParticle(
            CapturePlan.Shot shot, ClientLevel level, Vec3 at, List<String> diagnostics) {
        ResourceLocation id = ResourceLocation.parse(shot.id);
        JsonObject spec = shot.options == null ? new JsonObject() : shot.options;
        ParticleOptions options = ParticleOptionsFactory.build(id, spec, diagnostics);
        if (options == null) {
            return SpawnHandle.NONE;
        }
        int count = spec.has("count") ? spec.get("count").getAsInt() : 1;
        double dx = opt(spec, "dx", 0), dy = opt(spec, "dy", 0), dz = opt(spec, "dz", 0);
        double spread = opt(spec, "delta", 0);
        for (int i = 0; i < Math.max(1, count); i++) {
            double ox = spread == 0 ? 0 : (RANDOM.nextDouble() - 0.5) * spread;
            double oy = spread == 0 ? 0 : (RANDOM.nextDouble() - 0.5) * spread;
            double oz = spread == 0 ? 0 : (RANDOM.nextDouble() - 0.5) * spread;
            level.addParticle(options, at.x + ox, at.y + oy, at.z + oz, dx, dy, dz);
        }
        return SpawnHandle.NONE;
    }

    private static SpawnHandle spawnLevelEvent(
            CapturePlan.Shot shot, Vec3 at, net.minecraft.server.MinecraftServer server, List<String> diagnostics) {
        if (shot.event == null) {
            diagnostics.add("spawner: level_event shot " + shot.id + " has no event id");
            return SpawnHandle.NONE;
        }
        int event = shot.event;
        int data;
        if (shot.data_int != null) {
            data = shot.data_int;
        } else if (shot.data_block != null) {
            Block b = BuiltInRegistries.BLOCK.get(ResourceLocation.parse(shot.data_block));
            BlockState state = b == null ? Blocks.STONE.defaultBlockState() : b.defaultBlockState();
            data = Block.getId(state);
        } else {
            data = 0;
        }
        BlockPos pos = BlockPos.containing(at);
        server.execute(() -> server.overworld().levelEvent(event, pos, data));
        return SpawnHandle.NONE;
    }

    private static SpawnHandle spawnFx(
            CapturePlan.Shot shot, ClientLevel level, Vec3 at, List<String> diagnostics) {
        ResourceLocation id = ResourceLocation.parse(shot.id);
        FX fx = FXHelper.getFX(id);
        if (fx == null) {
            diagnostics.add("spawner: FX not found " + id + " (assets/<ns>/fx/*.fx)");
            return SpawnHandle.NONE;
        }
        BlockPos anchor = BlockPos.containing(at);
        BlockEffectExecutor executor = new BlockEffectExecutor(fx, level, anchor);
        // offset is relative to the anchor block pos — passing absolute coords
        // would double the position and drop the FX out of the world
        executor.setOffset(at.x - anchor.getX(), at.y - anchor.getY(), at.z - anchor.getZ());
        executor.setAllowMulti(true);
        executor.start();
        boolean stop = shot.stop_after == null || shot.stop_after;
        return () -> {
            if (stop && executor.getRuntime() != null) {
                executor.getRuntime().destroy(true);
            }
        };
    }

    private static SpawnHandle spawnQuasar(
            CapturePlan.Shot shot, Vec3 at, List<String> diagnostics) {
        try {
            var manager = foundry.veil.api.client.render.VeilRenderSystem.renderer().getParticleManager();
            ResourceLocation id = ResourceLocation.parse(shot.id);
            var emitter = manager.createEmitter(id);
            if (emitter == null) {
                diagnostics.add("spawner: quasar emitter not found " + id);
                return SpawnHandle.NONE;
            }
            emitter.setPosition(at);
            // emitters idle until force-spawned; without this the manager ticks
            // the emitter but it never produces particles
            emitter.setForceSpawn(true);
            manager.addParticleSystem(emitter);
            LAST_QUASAR_MANAGER = manager;
            LAST_QUASAR_EMITTER = emitter;
            diagnostics.add("spawner: quasar " + id + " forceSpawn=true");
            boolean stop = shot.stop_after == null || shot.stop_after;
            return () -> {
                if (stop) {
                    try {
                        emitter.remove();
                    } catch (Throwable ignored) {
                    }
                }
            };
        } catch (Throwable t) {
            diagnostics.add("spawner: quasar spawn failed for " + shot.id + " (veil present?): " + t);
            return SpawnHandle.NONE;
        }
    }

    private static double opt(JsonObject spec, String key, double def) {
        return spec.has(key) ? spec.get(key).getAsDouble() : def;
    }
}
