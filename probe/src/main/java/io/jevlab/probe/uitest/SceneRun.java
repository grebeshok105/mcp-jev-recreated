package io.jevlab.probe.uitest;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.lowdragmc.lowdraglib2.uitest.ScenarioBuilder;
import com.lowdragmc.lowdraglib2.uitest.TestContext;
import io.jevlab.probe.Paths;
import io.jevlab.probe.capture.CapturePlan;
import io.jevlab.probe.capture.Measurer;
import io.jevlab.probe.capture.ScenePlan;
import io.jevlab.probe.capture.Spawner;
import io.jevlab.probe.mixin.ParticleEngineAccessor;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

/**
 * Exact runtime playback for the scene lane. Reads
 * {@code <out>/scene/scene_plan.json} — a timed sequence of spawn steps —
 * replays the whole timeline once per requested camera angle and records
 * per-step spawn diagnostics, scene-level particle measurements and named
 * screenshots at the requested frame ticks.
 *
 * <p>Replay is deterministic: steps fire on fixed ticks of the scenario
 * clock (each {@code b.ticks(1)} is one client tick), so the same plan
 * produces the same sequence for every angle.
 */
public final class SceneRun {
    private static final java.util.Set<String> KNOWN_ANGLES = java.util.Set.of(
            "front", "back", "side", "side_right", "top", "threequarter", "low", "far");

    private final List<String> diagnostics = new ArrayList<>();
    private final JsonObject results = new JsonObject();

    public void define(ScenarioBuilder b) {
        ScenePlan loaded;
        try {
            loaded = Paths.sceneFile().toFile().exists()
                    ? ScenePlan.load(Paths.sceneFile())
                    : new ScenePlan();
        } catch (IOException e) {
            loaded = new ScenePlan();
            diagnostics.add("scene plan unreadable: " + e);
        }
        final ScenePlan plan = loaded;
        results.add("angles", new JsonObject());
        // bounded: duration ticks per angle + teleport/settle margin
        long est = (long) plan.duration * Math.max(1, plan.camera.angles.length);
        b.timeoutMs(Math.max(120_000L, est * 1000L + 120_000L));
        if (plan.steps.isEmpty()) {
            diagnostics.add("scene plan missing or has no steps: " + Paths.sceneFile());
            b.step("vfxlab:scene-write-empty", ctx -> finish(plan));
            return;
        }

        b.step("vfxlab:scene-init", ctx -> {
            Minecraft mc = ctx.mc();
            mc.options.hideGui = true;
            Paths.measurementsDir().toFile().mkdirs();
        });
        for (String cmd : sceneCommands(plan.scene)) {
            b.runCommand(cmd);
        }
        b.ticks(10);

        Map<Integer, List<ScenePlan.Step>> byTick = new HashMap<>();
        for (int i = 0; i < plan.steps.size(); i++) {
            ScenePlan.Step s = plan.steps.get(i);
            byTick.computeIfAbsent(s.at_tick, k -> new ArrayList<>()).add(s);
        }

        for (String angle : plan.camera.angles) {
            if (!KNOWN_ANGLES.contains(angle)) {
                diagnostics.add("scene: unknown angle '" + angle + "'");
                continue;
            }
            b.step("vfxlab:scene-cam@" + angle, ctx -> {
                Vec3 at = groundPoint(ctx.level(), plan.scene);
                ctx.put("anchor@" + angle, at);
                double[] cam = cameraFor(angle, at);
                ctx.put("cam@" + angle, cam);
                ctx.server().execute(() -> ctx.server().getCommands().performPrefixedCommand(
                        ctx.server().createCommandSourceStack(),
                        String.format("tp @p %.4f %.4f %.4f %.4f %.4f",
                                cam[0], cam[1], cam[2], cam[3], cam[4])));
                ctx.put("measurer@" + angle, new Measurer(plan.name + "@" + angle));
                ctx.put("handles@" + angle, new ArrayList<Spawner.SpawnHandle>());
                ctx.put("stepdiag@" + angle, new JsonArray());
            });
            b.ticks(4);
            b.step("vfxlab:scene-begin@" + angle, ctx -> {
                ((Measurer) ctx.get("measurer@" + angle)).begin();
                var p = ctx.player();
                diagnostics.add(String.format(
                        "scene@%s cam pos=%.2f,%.2f,%.2f yRot=%.1f xRot=%.1f",
                        angle, p.getX(), p.getY(), p.getZ(), p.getYRot(), p.getXRot()));
            });
            for (int t = 1; t <= plan.duration; t++) {
                final int tick = t;
                List<ScenePlan.Step> due = byTick.get(tick);
                if (due != null) {
                    b.step("vfxlab:scene-spawn t" + tick + "@" + angle, ctx -> {
                        Vec3 anchor = ctx.get("anchor@" + angle);
                        List<Spawner.SpawnHandle> handles = ctx.get("handles@" + angle);
                        JsonArray stepDiag = ctx.get("stepdiag@" + angle);
                        for (ScenePlan.Step s : due) {
                            List<String> sd = new ArrayList<>();
                            Vec3 at = anchor.add(s.pos[0], s.pos[1], s.pos[2]);
                            Spawner.SpawnHandle h = Spawner.spawn(
                                    s.shot, ctx.level(), at, ctx.server(), sd);
                            if (s.shot.stop_after == null || s.shot.stop_after) {
                                handles.add(h);
                            }
                            JsonObject rec = new JsonObject();
                            rec.addProperty("tick", tick);
                            rec.addProperty("id",
                                    s.shot.id != null ? s.shot.id : "step");
                            JsonArray d = new JsonArray();
                            sd.forEach(d::add);
                            rec.add("diagnostics", d);
                            stepDiag.add(rec);
                        }
                    });
                }
                b.ticks(1);
                b.step("vfxlab:scene-t" + tick + "@" + angle,
                        ctx -> ((Measurer) ctx.get("measurer@" + angle)).sampleTick());
                if (contains(plan.frames, tick)) {
                    b.screenshot(sanitize(plan.name) + "__" + angle + "__t" + tick);
                }
            }
            b.step("vfxlab:scene-stop@" + angle, ctx -> endAngle(ctx, plan, angle));
            b.ticks(2);
        }
        b.step("vfxlab:scene-write", ctx -> finish(plan));
    }

    private void endAngle(TestContext ctx, ScenePlan plan, String angle) {
        List<Spawner.SpawnHandle> handles = ctx.get("handles@" + angle);
        if (handles != null) {
            for (Spawner.SpawnHandle h : handles) {
                try {
                    h.stop();
                } catch (Throwable t) {
                    diagnostics.add("scene@" + angle + ": handle stop failed " + t);
                }
            }
        }
        ((ParticleEngineAccessor) ctx.mc().particleEngine).vfxlab$clearParticles();
        Measurer m = ctx.get("measurer@" + angle);
        Map<String, Object> fm = m.finish();
        JsonObject angleOut = new JsonObject();
        double[] cam = ctx.get("cam@" + angle);
        if (cam != null) {
            angleOut.addProperty("camera", String.format("%.2f,%.2f,%.2f,yaw=%.1f,pitch=%.1f",
                    cam[0], cam[1], cam[2], cam[3], cam[4]));
        }
        angleOut.addProperty("spawned", String.valueOf(fm.get("total_spawned")));
        angleOut.addProperty("peak_alive", String.valueOf(fm.get("peak_alive")));
        angleOut.addProperty("alive_at_end", String.valueOf(fm.get("alive_at_end")));
        angleOut.addProperty("first_visible_tick", String.valueOf(fm.get("first_visible_tick")));
        if (fm.containsKey("bounds_min")) {
            float[] mn = (float[]) fm.get("bounds_min");
            float[] mx = (float[]) fm.get("bounds_max");
            angleOut.addProperty("bounds_min", arr(mn));
            angleOut.addProperty("bounds_max", arr(mx));
        }
        JsonArray sd = ctx.get("stepdiag@" + angle);
        if (sd != null) {
            angleOut.add("steps", sd);
        }
        results.getAsJsonObject("angles").add(angle, angleOut);
    }

    private void finish(ScenePlan plan) {
        String out = System.getProperty("ldlib2.uitest.out", "");
        Path shots = Path.of(out).resolve("screenshots").resolve("vfxlab.4_scene");
        JsonObject framesIndex = new JsonObject();
        if (Files.isDirectory(shots)) {
            try (var stream = Files.list(shots)) {
                stream.filter(p -> p.toString().endsWith(".png")).forEach(p -> {
                    String name = p.getFileName().toString();
                    String label = name.substring(name.indexOf('_') + 1, name.length() - 4);
                    int us = label.indexOf("__");
                    if (us >= 0) {
                        String rest = label.substring(us + 2);
                        int us2 = rest.lastIndexOf("__");
                        String angle = us2 < 0 ? rest : rest.substring(0, us2);
                        JsonObject angles = results.getAsJsonObject("angles");
                        JsonObject angleOut = angles == null ? null
                                : angles.getAsJsonObject(angle);
                        if (angleOut != null) {
                            JsonArray arr = angleOut.has("frames")
                                    ? angleOut.getAsJsonArray("frames") : new JsonArray();
                            arr.add(p.toAbsolutePath().toString());
                            angleOut.add("frames", arr);
                        }
                    }
                    framesIndex.addProperty(label, p.toAbsolutePath().toString());
                });
            } catch (IOException e) {
                diagnostics.add("scene frame index scan failed: " + e);
            }
        } else {
            diagnostics.add("runner screenshots dir missing: " + shots);
        }
        results.addProperty("name", plan.name);
        results.addProperty("duration", plan.duration);
        results.addProperty("step_count", plan.steps.size());
        try {
            ScenePlan.writeJson(Paths.measurementsDir().resolve("scene_frames_index.json"),
                    framesIndex);
            ScenePlan.writeJson(Paths.sceneResultsFile(), results);
            ScenePlan.writeJson(Paths.diagnosticsFile(), diagnostics);
        } catch (IOException e) {
            System.err.println("[vfxlab] writing scene results failed: " + e);
        }
        Minecraft.getInstance().options.hideGui = false;
    }

    private static List<String> sceneCommands(ScenePlan.Scene scene) {
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

    private static Vec3 groundPoint(Level level, ScenePlan.Scene scene) {
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
