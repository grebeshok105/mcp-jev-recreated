package io.jevlab.probe.dump;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.jevlab.probe.Paths;
import io.jevlab.probe.mixin.ParticleEngineAccessor;
import java.io.IOException;
import java.io.Writer;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import net.minecraft.client.Minecraft;
import net.minecraft.core.Registry;
import net.minecraft.core.particles.SimpleParticleType;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.block.LevelEvent;
import com.google.gson.Gson;

/**
 * Dumps the runtime VFX surface to JSON under {@link Paths#dumpDir()}.
 * Runs inside the client environment so client-only bindings (particle
 * factories, photon FX index, quasar emitters) are visible.
 */
public final class RegistryDump {
    private static final Gson GSON = new Gson();

    private RegistryDump() {}

    public static List<String> dumpAll() {
        List<String> diagnostics = new ArrayList<>();
        try {
            Files.createDirectories(Paths.dumpDir());
            write("particle_types.json", particleTypes(diagnostics));
            write("level_events.json", levelEvents());
            write("particle_providers.json", providers(diagnostics));
            write("photon.json", photon(diagnostics));
            write("resource_index.json", resourceIndex(diagnostics));
        } catch (IOException e) {
            diagnostics.add("dump io failure: " + e);
        }
        return diagnostics;
    }

    private static JsonObject particleTypes(List<String> diagnostics) {
        JsonObject root = new JsonObject();
        JsonArray arr = new JsonArray();
        Map<String, Integer> byNs = new TreeMap<>();
        for (var type : BuiltInRegistries.PARTICLE_TYPE) {
            ResourceLocation id = BuiltInRegistries.PARTICLE_TYPE.getKey(type);
            JsonObject o = new JsonObject();
            o.addProperty("id", id.toString());
            o.addProperty("namespace", id.getNamespace());
            o.addProperty("class", type.getClass().getName());
            o.addProperty("parameterized", !(type instanceof SimpleParticleType));
            arr.add(o);
            byNs.merge(id.getNamespace(), 1, Integer::sum);
        }
        root.add("types", arr);
        JsonObject counts = new JsonObject();
        byNs.forEach(counts::addProperty);
        root.add("by_namespace", counts);
        return root;
    }

    private static JsonObject levelEvents() {
        JsonObject root = new JsonObject();
        JsonArray arr = new JsonArray();
        for (Field f : LevelEvent.class.getFields()) {
            if (!Modifier.isStatic(f.getModifiers()) || f.getType() != int.class) {
                continue;
            }
            try {
                JsonObject o = new JsonObject();
                o.addProperty("name", f.getName());
                o.addProperty("id", f.getInt(null));
                arr.add(o);
            } catch (IllegalAccessException ignored) {
            }
        }
        root.add("events", arr);
        return root;
    }

    private static JsonObject providers(List<String> diagnostics) {
        JsonObject root = new JsonObject();
        JsonArray arr = new JsonArray();
        try {
            var providers = ((ParticleEngineAccessor) Minecraft.getInstance().particleEngine).vfxlab$getProviders();
            providers.forEach((key, provider) -> {
                var type = BuiltInRegistries.PARTICLE_TYPE.byId(key);
                ResourceLocation id = type == null
                        ? ResourceLocation.withDefaultNamespace("unknown_" + key)
                        : BuiltInRegistries.PARTICLE_TYPE.getKey(type);
                JsonObject o = new JsonObject();
                o.addProperty("id", id.toString());
                o.addProperty("factory", provider == null ? "null" : provider.getClass().getName());
                arr.add(o);
            });
        } catch (Throwable t) {
            diagnostics.add("providers dump failed: " + t);
        }
        root.add("providers", arr);
        return root;
    }

    private static JsonObject photon(List<String> diagnostics) {
        JsonObject root = new JsonObject();
        try {
            JsonArray fx = new JsonArray();
            for (ResourceLocation id : com.lowdragmc.photon.client.fx.FXHelper.listAllFX()) {
                fx.add(id.toString());
            }
            root.add("fx", fx);
        } catch (Throwable t) {
            diagnostics.add("photon fx list failed: " + t);
        }
        try {
            JsonObject registries = new JsonObject();
            for (Field f : com.lowdragmc.photon.PhotonRegistries.class.getFields()) {
                if (!Modifier.isStatic(f.getModifiers()) || !Registry.class.isAssignableFrom(f.getType())) {
                    continue;
                }
                Registry<?> reg = (Registry<?>) f.get(null);
                if (reg == null) continue;
                JsonArray keys = new JsonArray();
                for (var key : reg.keySet()) {
                    keys.add(key.toString());
                }
                registries.add(reg.key().location().toString(), keys);
            }
            root.add("registries", registries);
        } catch (Throwable t) {
            diagnostics.add("photon registries dump failed: " + t);
        }
        return root;
    }

    private static JsonObject resourceIndex(List<String> diagnostics) {
        JsonObject root = new JsonObject();
        var rm = Minecraft.getInstance().getResourceManager();
        String[][] groups = {
            {"quasar_emitters", "quasar/emitters", ".json"},
            {"vfx_params", "vfx", ".json"},
            {"particle_defs", "particles", ".json"},
            {"particle_textures", "textures/particle", ".png"},
            {"photon_textures", "textures", ".png"},
            {"photon_models", "models", ".obj"},
            {"photon_shaders", "shaders", ".json"},
            {"fx", "fx", ".fx"},
            {"vfx_textures", "textures/vfx", ".png"},
        };
        for (String[] g : groups) {
            try {
                JsonArray arr = new JsonArray();
                rm.listResources(g[1], p -> p.getPath().endsWith(g[2])).keySet().forEach(
                        id -> arr.add(id.toString()));
                root.add(g[0], arr);
            } catch (Throwable t) {
                diagnostics.add("resource index " + g[0] + " failed: " + t);
            }
        }
        return root;
    }

    private static void write(String name, JsonObject value) throws IOException {
        try (Writer w = Files.newBufferedWriter(Paths.dumpDir().resolve(name))) {
            GSON.toJson(value, w);
        }
    }
}
