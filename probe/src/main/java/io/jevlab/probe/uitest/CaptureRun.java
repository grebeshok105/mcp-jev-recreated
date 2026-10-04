package io.jevlab.probe.uitest;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.lowdragmc.lowdraglib2.uitest.ScenarioBuilder;
import com.lowdragmc.lowdraglib2.uitest.TestContext;
import io.jevlab.probe.Paths;
import io.jevlab.probe.capture.CapturePlan;
import io.jevlab.probe.capture.Measurer;
import io.jevlab.probe.capture.Spawner;
import io.jevlab.probe.mixin.ParticleEngineAccessor;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

/**
 * Plan-driven capture compiled into uitest steps: reads {@code <out>/capture_plan.json},
 * teleports the camera around each shot, records per-tick particle measurements and
 * named screenshots, then writes {@code frames/}, {@code measurements/} and
 * {@code probe_diagnostics.json} under {@code -Dvfxlab.outdir}.
 */
public final class CaptureRun {
    private static final java.util.Set<String> KNOWN_ANGLES = java.util.Set.of(
            "front", "back", "side", "side_right", "top", "threequarter", "low", "far");

    private final List<String> diagnostics = new ArrayList<>();
    private final JsonObject results = new JsonObject();
    private Measurer measurer;
    private Spawner.SpawnHandle handle = Spawner.SpawnHandle.NONE;

    public void define(ScenarioBuilder b) {
        CapturePlan loaded;
        try {
            loaded = Paths.capturePlanFile().toFile().exists()
                    ? CapturePlan.load(Paths.capturePlanFile())
                    : new CapturePlan();
        } catch (IOException e) {
            loaded = new CapturePlan();
            diagnostics.add("capture plan unreadable: " + e);
        }
        final CapturePlan plan = loaded;
        // default 120s per-scenario budget cannot hold a full catalog sweep —
        // 197 shots × angles × ticks needs tens of minutes.
        b.timeoutMs(5_400_000L);
        if (plan.shots.isEmpty()) {
            diagnostics.add("capture plan missing or empty: " + Paths.capturePlanFile());
            b.step("vfxlab:write-empty", ctx -> finish());
            return;
        }

        b.step("vfxlab:init", ctx -> {
            Minecraft mc = ctx.mc();
            mc.options.hideGui = true;
            Paths.framesDir().toFile().mkdirs();
            Paths.measurementsDir().toFile().mkdirs();
            try {
                Files.createDirectories(Paths.dumpDir());
            } catch (IOException ignored) {
            }
        });
        for (String cmd : sceneCommands(plan.scene)) {
            b.runCommand(cmd);
        }
        b.ticks(10);

        for (CapturePlan.Shot shot : plan.shots) {
            int[] frames = shot.frames != null ? shot.frames : plan.defaults.frames;
            String[] angles = shot.angles != null ? shot.angles : plan.defaults.angles;
            int maxFrame = 0;
            for (int f : frames) {
                maxFrame = Math.max(maxFrame, f);
            }
            if (maxFrame <= 0) {
                diagnostics.add("shot " + shot.id + ": no positive frame ticks");
                continue;
            }
            for (String angle : angles) {
                if (!KNOWN_ANGLES.contains(angle)) {
                    diagnostics.add("shot " + shot.id + ": unknown angle '" + angle + "'");
                    continue;
                }
                // resolve the anchor + camera on the live level, then teleport the
                // player on the server thread (integrated server shares the world)
                b.step("vfxlab:cam " + shot.id + "@" + angle, ctx -> {
                    Vec3 at = groundPoint(ctx.level(), plan.scene);
                    ctx.put("at@" + shot.id, at);
                    double[] cam = cameraFor(angle, at);
                    ctx.put("cam@" + shot.id + "@" + angle, cam);
                    ctx.server().execute(() -> ctx.server().getCommands().performPrefixedCommand(
                            ctx.server().createCommandSourceStack(),
                            String.format("tp @p %.4f %.4f %.4f %.4f %.4f",
                                    cam[0], cam[1], cam[2], cam[3], cam[4])));
                });
                b.ticks(4);
                b.step("vfxlab:spawn " + shot.id + "@" + angle, ctx -> {
                    List<String> shotDiag = new ArrayList<>();
                    ctx.put("diag@" + shot.id + "@" + angle, shotDiag);
                    var p = ctx.player();
                    shotDiag.add(String.format("cam_actual pos=%.2f,%.2f,%.2f yRot=%.1f xRot=%.1f",
                            p.getX(), p.getY(), p.getZ(), p.getYRot(), p.getXRot()));
                    Vec3 atv = ctx.get("at@" + shot.id);
                    shotDiag.add("at=" + vec(atv));
                    measurer = new Measurer(shot.id + "@" + angle);
                    measurer.begin();
                    handle = Spawner.spawn(shot, ctx.level(), atv, ctx.server(), shotDiag);
                });
                for (int t = 1; t <= maxFrame; t++) {
                    final int tick = t;
                    b.ticks(1);
                    b.step("vfxlab:t" + tick + " " + shot.id + "@" + angle, ctx -> {
                        measurer.sampleTick();
                        if ("quasar_emitter".equals(shot.kind) && Spawner.LAST_QUASAR_MANAGER != null) {
                            var mgr = (foundry.veil.api.quasar.particle.ParticleSystemManager)
                                    Spawner.LAST_QUASAR_MANAGER;
                            var em = (foundry.veil.api.quasar.particle.ParticleEmitter)
                                    Spawner.LAST_QUASAR_EMITTER;
                            var d = (List<String>) ctx.get("diag@" + shot.id + "@" + angle);
                            if (d != null) {
                                d.add("t" + tick + " mgrParticles=" + mgr.getParticleCount()
                                        + " emitParticles=" + em.getParticleCount()
                                        + " emitters=" + mgr.getEmitterCount()
                                        + " removed=" + em.isRemoved());
                            }
                        }
                    });
                    if (contains(frames, tick)) {
                        // runner-native capture: grabs the main render target at the
                        // pipeline point the harness controls — a plain
                        // Screenshot.takeScreenshot inside a step can read a buffer
                        // before the particle pass and silently miss the subject.
                        b.screenshot(sanitize(shot.id) + "__" + angle + "__t" + tick);
                    }
                }
                b.step("vfxlab:stop " + shot.id + "@" + angle, ctx -> endAngle(ctx, plan, shot, angle));
                b.ticks(2);
            }
        }
        b.step("vfxlab:write", ctx -> finish());
    }

    private void endAngle(TestContext ctx, CapturePlan plan, CapturePlan.Shot shot, String angle) {
        try {
            handle.stop();
        } catch (Throwable t) {
            diagnostics.add(shot.id + "@" + angle + ": teardown failed " + t);
        }
        handle = Spawner.SpawnHandle.NONE;
        ((ParticleEngineAccessor) ctx.mc().particleEngine).vfxlab$clearParticles();
        Map<String, Object> m = measurer.finish();
        @SuppressWarnings("unchecked")
        List<String> shotDiag = (List<String>) ctx.get("diag@" + shot.id + "@" + angle);
        JsonObject shotOut = (JsonObject) results.get(sanitize(shot.id));
        if (shotOut == null) {
            shotOut = new JsonObject();
            shotOut.addProperty("id", shot.id);
            shotOut.addProperty("kind", shot.kind);
            Vec3 at = ctx.get("at@" + shot.id);
            if (at != null) {
                shotOut.addProperty("pos", vec(at));
            }
            shotOut.add("angles", new JsonObject());
            results.add(sanitize(shot.id), shotOut);
        }
        JsonObject angleOut = new JsonObject();
        double[] cam = ctx.get("cam@" + shot.id + "@" + angle);
        if (cam != null) {
            angleOut.addProperty("camera", String.format("%.2f,%.2f,%.2f,yaw=%.1f,pitch=%.1f",
                    cam[0], cam[1], cam[2], cam[3], cam[4]));
        }
        angleOut.addProperty("spawned", String.valueOf(m.get("total_spawned")));
        angleOut.addProperty("peak_alive", String.valueOf(m.get("peak_alive")));
        angleOut.addProperty("alive_at_end", String.valueOf(m.get("alive_at_end")));
        angleOut.addProperty("first_visible_tick", String.valueOf(m.get("first_visible_tick")));
        if (m.containsKey("bounds_min")) {
            angleOut.addProperty("bounds_min", arr((float[]) m.get("bounds_min")));
            angleOut.addProperty("bounds_max", arr((float[]) m.get("bounds_max")));
        }
        JsonArray d = new JsonArray();
        if (shotDiag != null) {
            shotDiag.forEach(d::add);
            shotDiag.forEach(s -> diagnostics.add(shot.id + "@" + angle + ": " + s));
        }
        angleOut.add("diagnostics", d);
        shotOut.getAsJsonObject("angles").add(angle, angleOut);
    }

    private void finish() {
        // runner captures land under <ldlib2.uitest.out>/screenshots/<scenario>/
        // as <stepIndex>_<name>.png — index them by shot/angle/tick suffix so the
        // python pipeline gets stable references without globbing.
        String out = System.getProperty("ldlib2.uitest.out", "");
        Path shots = java.nio.file.Path.of(out).resolve("screenshots").resolve("vfxlab.3_capture");
        JsonObject framesIndex = new JsonObject();
        if (Files.isDirectory(shots)) {
            try (var stream = Files.list(shots)) {
                stream.filter(p -> p.toString().endsWith(".png")).forEach(p -> {
                    String name = p.getFileName().toString();
                    String label = name.substring(name.indexOf('_') + 1, name.length() - 4);
                    int us = label.indexOf("__");
                    String shotKey = us < 0 ? label : label.substring(0, us);
                    JsonObject shot = results.getAsJsonObject(shotKey);
                    if (shot != null) {
                        JsonObject angles = shot.getAsJsonObject("angles");
                        String rest = label.substring(us + 2);
                        String angle = rest.substring(0, rest.lastIndexOf("__"));
                        JsonObject angleOut = angles.getAsJsonObject(angle);
                        if (angleOut != null) {
                            JsonArray arr = angleOut.has("frames") ? angleOut.getAsJsonArray("frames")
                                    : new JsonArray();
                            arr.add(p.toAbsolutePath().toString());
                            angleOut.add("frames", arr);
                        }
                    }
                    framesIndex.addProperty(label, p.toAbsolutePath().toString());
                });
            } catch (IOException e) {
                diagnostics.add("frame index scan failed: " + e);
            }
        } else {
            diagnostics.add("runner screenshots dir missing: " + shots);
        }
        try {
            CapturePlan.writeJson(Paths.measurementsDir().resolve("frames_index.json"), framesIndex);
            CapturePlan.writeJson(Paths.measurementsDir().resolve("capture_results.json"), results);
            CapturePlan.writeJson(Paths.diagnosticsFile(), diagnostics);
        } catch (IOException e) {
            System.err.println("[vfxlab] writing capture results failed: " + e);
        }
        Minecraft.getInstance().options.hideGui = false;
    }

    private static List<String> sceneCommands(CapturePlan.Scene scene) {
        return List.of(
                "gamerule doDaylightCycle false",
                "gamerule doWeatherCycle false",
                "gamerule doMobSpawning false",
                "gamerule mobGriefing false",
                "gamerule sendCommandFeedback false",
                "time set " + scene.time,
                "weather " + scene.weather,
                "gamemode creative @p");
    }

    /** scene.pos = [x, height-above-ground, z]. */
    private static Vec3 groundPoint(Level level, CapturePlan.Scene scene) {
        double x = scene.pos[0];
        double z = scene.pos[2];
        double lift = scene.pos.length > 1 ? scene.pos[1] : 2.0;
        for (int scan = level.getMaxBuildHeight() - 40; scan > level.getMinBuildHeight(); scan--) {
            BlockPos p = BlockPos.containing(x, scan, z);
            if (!level.getBlockState(p).isAir()) {
                return new Vec3(x, scan + 1.0 + lift, z);
            }
        }
        return new Vec3(x, level.getSeaLevel() + lift, z);
    }

    /** camera position+rotation for a named angle around target {@code at}: {x,y,z,yaw,pitch}. */
    private static double[] cameraFor(String angle, Vec3 at) {
        double h = 3.5;
        return switch (angle) {
            case "front" -> lookAt(at.x, at.y + 1.4, at.z + h, at);
            case "back" -> lookAt(at.x, at.y + 1.4, at.z - h, at);
            case "side" -> lookAt(at.x - h, at.y + 1.4, at.z, at);
            case "side_right" -> lookAt(at.x + h, at.y + 1.4, at.z, at);
            case "top" -> lookAt(at.x, at.y + 4.5, at.z, at);
            case "threequarter" -> lookAt(at.x - 2.8, at.y + 2.4, at.z + 2.8, at);
            case "low" -> lookAt(at.x, at.y + 0.35, at.z + h, at);
            case "far" -> lookAt(at.x, at.y + 1.6, at.z + 8, at);
            default -> null;
        };
    }

    private static double[] lookAt(double cx, double cy, double cz, Vec3 at) {
        double dx = at.x - cx;
        double dy = at.y + 0.5 - cy;
        double dz = at.z - cz;
        double hd = Math.hypot(dx, dz);
        float yaw = (float) Math.toDegrees(Math.atan2(-dx, dz));
        float pitch = (float) -Math.toDegrees(Math.atan2(dy, hd));
        return new double[] {cx, cy, cz, yaw, pitch};
    }

    private static String vec(Vec3 v) {
        return String.format("%.3f,%.3f,%.3f", v.x, v.y, v.z);
    }

    private static String arr(float[] a) {
        return String.format("%.3f,%.3f,%.3f", a[0], a[1], a[2]);
    }

    private static String sanitize(String id) {
        return id.replace(':', '_').replace('/', '_');
    }

    private static boolean contains(int[] a, int v) {
        for (int x : a) {
            if (x == v) {
                return true;
            }
        }
        return false;
    }
}
