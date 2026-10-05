package io.jevlab.probe.capture;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import java.util.Map;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.phys.Vec3;

/**
 * Resolves a scene-v2 anchor expression to a world position + look frame.
 *
 * <p>Anchor expressions (JSON):
 * <pre>{@code
 *   "player.head"                                     // shorthand string
 *   {"anchor":"player.head","offset":[0,0,0.25],"direction":"player.look"}
 *   {"anchor":"player.look","distance":8,"direction":"player.look"}
 *   {"anchor":"ref:zap"}                              // spawn pos of a named step
 * }</pre>
 *
 * <p>Anchors: scene | player | player.feet | player.chest | player.head |
 * player.look | camera | ref:&lt;name&gt;. `player.head`, `player.look` and
 * `camera` are aliases (eye position); `player` = `player.feet`. Offsets
 * are in the anchor's local frame (x right, y up, z forward) rotated by
 * the resolved direction. `distance` pushes along the resolved direction
 * (world = +z when direction is absent).
 *
 * <p>Directions: "world" | "player.look" | [yaw,pitch] | {"face":&lt;anchor expr&gt;}.
 */
public final class AnchorResolver {
    private AnchorResolver() {}

    public record Resolved(Vec3 pos, float yaw, float pitch) {}

    public static Resolved resolve(
            JsonElement spec, LocalPlayer player, Vec3 sceneAnchor,
            Map<String, Vec3> refs, java.util.List<String> diagnostics) {
        JsonObject obj;
        if (spec.isJsonPrimitive()) {
            obj = new JsonObject();
            obj.addProperty("anchor", spec.getAsString());
        } else {
            obj = spec.getAsJsonObject();
        }
        String anchor = obj.has("anchor") ? obj.get("anchor").getAsString() : "scene";
        Vec3 base = basePoint(anchor, player, sceneAnchor, refs, diagnostics);
        float[] dir = direction(obj.get("direction"), base, player,
                sceneAnchor, refs, diagnostics);
        Vec3 p = base;
        if (obj.has("offset")) {
            JsonArray off = obj.getAsJsonArray("offset");
            p = p.add(rotateOffset(off.get(0).getAsDouble(), off.get(1).getAsDouble(),
                    off.get(2).getAsDouble(), dir[0], dir[1]));
        }
        if (obj.has("distance")) {
            double d = obj.get("distance").getAsDouble();
            Vec3 fwd = forward(dir[0], dir[1]);
            p = p.add(fwd.scale(d));
        }
        return new Resolved(p, dir[0], dir[1]);
    }

    private static Vec3 basePoint(String anchor, LocalPlayer player, Vec3 sceneAnchor,
                                  Map<String, Vec3> refs, java.util.List<String> diagnostics) {
        if (player == null || anchor.equals("scene") || anchor.startsWith("ref:")) {
            if (anchor.startsWith("ref:")) {
                Vec3 r = refs.get(anchor.substring(4));
                if (r == null) {
                    diagnostics.add("anchor '" + anchor + "': ref not yet resolved");
                    return sceneAnchor;
                }
                return r;
            }
            if (player == null && !anchor.equals("scene")) {
                diagnostics.add("anchor '" + anchor
                        + "' needs a player but none is present");
            }
            return sceneAnchor;
        }
        return switch (anchor) {
            case "player", "player.feet" -> player.position();
            case "player.chest" -> player.position().add(0, 1.2, 0);
            case "player.head", "player.look", "camera" -> player.getEyePosition();
            default -> {
                diagnostics.add("anchor: unknown '" + anchor + "' — falling back to scene");
                yield sceneAnchor;
            }
        };
    }

    private static float[] direction(JsonElement dir, Vec3 from, LocalPlayer player,
                                     Vec3 sceneAnchor, Map<String, Vec3> refs,
                                     java.util.List<String> diagnostics) {
        if (dir == null || dir.isJsonNull()) {
            return new float[] {0, 0};
        }
        if (dir.isJsonPrimitive()) {
            return switch (dir.getAsString()) {
                case "world" -> new float[] {0, 0};
                case "player.look" -> player != null
                        ? new float[] {player.getYRot(), player.getXRot()}
                        : new float[] {0, 0};
                default -> {
                    diagnostics.add("direction: unknown '" + dir.getAsString() + "'");
                    yield new float[] {0, 0};
                }
            };
        }
        if (dir.isJsonArray()) {
            JsonArray a = dir.getAsJsonArray();
            return new float[] {a.get(0).getAsFloat(), a.get(1).getAsFloat()};
        }
        if (dir.isJsonObject() && dir.getAsJsonObject().has("face")) {
            Resolved target = resolve(dir.getAsJsonObject().get("face"), player,
                    sceneAnchor, refs, diagnostics);
            return faceYawPitch(from, target.pos());
        }
        diagnostics.add("direction: unsupported form " + dir);
        return new float[] {0, 0};
    }

    /** yaw/pitch that looks from `from` toward `to` (Minecraft rotation space). */
    public static float[] faceYawPitch(Vec3 from, Vec3 to) {
        double dx = to.x - from.x;
        double dy = to.y - from.y;
        double dz = to.z - from.z;
        double hd = Math.hypot(dx, dz);
        float yaw = (float) Math.toDegrees(Math.atan2(-dx, dz));
        float pitch = (float) -Math.toDegrees(Math.atan2(dy, Math.max(hd, 1e-6)));
        return new float[] {yaw, pitch};
    }

    /** unit forward vector for Minecraft yaw/pitch (deg). */
    public static Vec3 forward(float yaw, float pitch) {
        double yr = Math.toRadians(yaw), pr = Math.toRadians(pitch);
        return new Vec3(-Math.sin(yr) * Math.cos(pr), -Math.sin(pr),
                Math.cos(yr) * Math.cos(pr));
    }

    /** rotate a local-frame offset (x right, y up, z forward) by yaw/pitch (deg). */
    public static Vec3 rotateOffset(double lx, double ly, double lz, float yaw, float pitch) {
        double yr = Math.toRadians(yaw), pr = Math.toRadians(pitch);
        Vec3 fwd = forward(yaw, pitch);
        Vec3 right = new Vec3(-Math.cos(yr), 0, -Math.sin(yr));
        Vec3 up = new Vec3(-Math.sin(yr) * Math.sin(pr), Math.cos(pr),
                Math.cos(yr) * Math.sin(pr));
        return right.scale(lx).add(up.scale(ly)).add(fwd.scale(lz));
    }
}
