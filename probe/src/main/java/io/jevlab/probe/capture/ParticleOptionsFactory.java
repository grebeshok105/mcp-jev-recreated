package io.jevlab.probe.capture;

import com.google.gson.JsonObject;
import java.util.List;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.BlockParticleOption;
import net.minecraft.core.particles.ColorParticleOption;
import net.minecraft.core.particles.DustColorTransitionOptions;
import net.minecraft.core.particles.DustParticleOptions;
import net.minecraft.core.particles.ItemParticleOption;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.core.particles.ParticleType;
import net.minecraft.core.particles.SculkChargeParticleOptions;
import net.minecraft.core.particles.ShriekParticleOption;
import net.minecraft.core.particles.SimpleParticleType;
import net.minecraft.core.particles.VibrationParticleOption;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.gameevent.BlockPositionSource;
import org.joml.Vector3f;

/** Builds {@link ParticleOptions} for a registry particle type from the plan spec. */
public final class ParticleOptionsFactory {
    private ParticleOptionsFactory() {}

    /**
     * Returns a spawnable {@link ParticleOptions} for {@code id}, or {@code null} when the
     * type is not parameterized and needs no wrapper (simple types are returned as-is), or
     * cannot be satisfied by the implemented option families (recorded in diagnostics).
     */
    public static ParticleOptions build(ResourceLocation id, JsonObject spec, List<String> diagnostics) {
        ParticleType<?> type = BuiltInRegistries.PARTICLE_TYPE.get(id);
        if (type == null) {
            diagnostics.add("particle_options: unknown particle type " + id);
            return null;
        }
        spec = spec == null ? new JsonObject() : spec;
        String name = id.toString();

        if (type instanceof SimpleParticleType simple) {
            return simple;
        }
        try {
            return switch (name) {
                case "minecraft:dust" -> dust(spec);
                case "minecraft:dust_color_transition" -> dustTransition(spec);
                case "minecraft:block", "minecraft:block_marker", "minecraft:falling_dust",
                        "minecraft:dust_pillar" -> blockOption(type, spec);
                case "minecraft:item" -> new ItemParticleOption(asItemType(type), itemStack(spec));
                case "minecraft:entity_effect" -> colorOption(type, spec);
                case "minecraft:shriek" -> new ShriekParticleOption(intOr(spec, "delay", 0));
                case "minecraft:sculk_charge" -> new SculkChargeParticleOptions(floatOr(spec, "roll", 0f));
                case "minecraft:vibration" -> new VibrationParticleOption(
                        new BlockPositionSource(BlockPos.containing(vecOr(spec, "destination", 0, -60, 0))),
                        intOr(spec, "arrival_in_ticks", 20));
                default -> {
                    diagnostics.add("particle_options: no builder for parameterized type " + name
                            + " (" + type.getClass().getName() + ")");
                    yield null;
                }
            };
        } catch (Throwable t) {
            diagnostics.add("particle_options: builder failed for " + name + ": " + t);
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private static <T extends ParticleOptions> ParticleType<T> asItemType(ParticleType<?> t) {
        return (ParticleType<T>) t;
    }

    private static DustParticleOptions dust(JsonObject spec) {
        float[] rgb = rgbOr(spec, "color", 1f, 0f, 0f);
        return new DustParticleOptions(new Vector3f(rgb[0], rgb[1], rgb[2]), floatOr(spec, "scale", 1f));
    }

    private static DustColorTransitionOptions dustTransition(JsonObject spec) {
        float[] from = rgbOr(spec, "from_color", 1f, 0f, 0f);
        float[] to = rgbOr(spec, "to_color", 0f, 0f, 1f);
        return new DustColorTransitionOptions(
                new Vector3f(from[0], from[1], from[2]), new Vector3f(to[0], to[1], to[2]),
                floatOr(spec, "scale", 1f));
    }

    @SuppressWarnings("unchecked")
    private static <T extends ParticleOptions> BlockParticleOption blockOption(ParticleType<?> type, JsonObject spec) {
        Block block = BuiltInRegistries.BLOCK.get(ResourceLocation.parse(
                spec.has("block") ? spec.get("block").getAsString() : "minecraft:stone"));
        BlockState state = block == null ? Blocks.STONE.defaultBlockState() : block.defaultBlockState();
        return new BlockParticleOption((ParticleType<BlockParticleOption>) type, state);
    }

    @SuppressWarnings("unchecked")
    private static <T extends ParticleOptions> ColorParticleOption colorOption(ParticleType<?> type, JsonObject spec) {
        // spec: {"color":[r,g,b] 0..1 floats} or {"color":<ARGB int>} ; alpha optional via "alpha" 0..255
        int alpha = spec.has("alpha") ? spec.get("alpha").getAsInt() : 255;
        int argb;
        if (spec.has("color") && spec.get("color").isJsonArray()) {
            float[] rgb = rgbOr(spec, "color", 1f, 0f, 0f);
            argb = (alpha << 24) | ((int) (rgb[0] * 255) << 16) | ((int) (rgb[1] * 255) << 8) | (int) (rgb[2] * 255);
        } else if (spec.has("color")) {
            argb = spec.get("color").getAsInt();
        } else {
            argb = (alpha << 24) | 0xFF0000;
        }
        return ColorParticleOption.create((ParticleType<ColorParticleOption>) type, argb);
    }

    private static ItemStack itemStack(JsonObject spec) {
        var item = BuiltInRegistries.ITEM.get(ResourceLocation.parse(
                spec.has("item") ? spec.get("item").getAsString() : "minecraft:stone"));
        return item == null ? new ItemStack(Blocks.STONE) : new ItemStack(item);
    }

    private static float[] rgbOr(JsonObject spec, String key, float r, float g, float b) {
        if (spec.has(key) && spec.get(key).isJsonArray() && spec.get(key).getAsJsonArray().size() >= 3) {
            var a = spec.get(key).getAsJsonArray();
            return new float[] {a.get(0).getAsFloat(), a.get(1).getAsFloat(), a.get(2).getAsFloat()};
        }
        return new float[] {r, g, b};
    }

    private static net.minecraft.world.phys.Vec3 vecOr(JsonObject spec, String key, double x, double y, double z) {
        if (spec.has(key) && spec.get(key).isJsonArray() && spec.get(key).getAsJsonArray().size() >= 3) {
            var a = spec.get(key).getAsJsonArray();
            return new net.minecraft.world.phys.Vec3(a.get(0).getAsDouble(), a.get(1).getAsDouble(), a.get(2).getAsDouble());
        }
        return new net.minecraft.world.phys.Vec3(x, y, z);
    }

    private static int intOr(JsonObject spec, String key, int def) {
        return spec.has(key) ? spec.get(key).getAsInt() : def;
    }

    private static float floatOr(JsonObject spec, String key, float def) {
        return spec.has(key) ? spec.get(key).getAsFloat() : def;
    }
}
