package io.jevlab.probe.capture;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Playback plan for the scene lane (`<out>/scene/scene_plan.json`), produced
 * by the python side (jevlab.scene.compile). Unlike CapturePlan — one shot at
 * a time per angle — a scene fires many steps on a tick timeline while the
 * camera stays put, so the same timeline replays once per requested angle.
 * v2 adds commands (tick-scheduled server commands), anchor expressions,
 * follow/tracks and ref wiring — all compiled in python, executed verbatim.
 */
public final class ScenePlan {
    public int version = 1;
    public String name = "scene";
    public Scene scene = new Scene();
    public Camera camera = new Camera();
    public int[] frames = {3, 8, 20};
    public int duration = 60;
    public List<Step> steps = new ArrayList<>();
    /** server commands fired on ticks — e.g. moving the player mid-scene. */
    public List<Cmd> commands = new ArrayList<>();

    public static final class Cmd {
        public int at_tick = 0;
        public String command = "";
    }

    public static final class Scene {
        public double[] pos = {8.5, 2, 8.5};
        public int time = 6000;
        public String weather = "clear";
    }

    public static final class Camera {
        public String[] angles = {"front"};
    }

    public static final class Step {
        public int at_tick = 0;
        /** optional name — makes the step addressable as "ref:<name>". */
        public String name;
        /** v1 compat: local offset added to the resolved scene anchor. */
        public double[] pos = {0, 0, 0};
        /**
         * v2 anchor expression (string or object; see AnchorResolver).
         * When set it fully describes the spawn origin; `pos` then acts as a
         * final local offset applied on top.
         */
        public com.google.gson.JsonElement at;
        /** v2 target expression — the step's direction faces this point. */
        public com.google.gson.JsonElement to;
        /** entity to follow per tick: "player" (the only probe entity). */
        public String follow;
        /**
         * keyframe tracks applied to persistent handles per tick:
         * {"pos":[[t,x,y,z],...], "rotation":[[t,yaw,pitch],...],
         *  "scale":[[t,s],...]}
         */
        public com.google.gson.JsonObject track;
        /** spawn spec — same shape as CapturePlan.Shot. */
        public CapturePlan.Shot shot = new CapturePlan.Shot();
    }

    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    public static ScenePlan load(Path path) throws IOException {
        try (Reader r = Files.newBufferedReader(path)) {
            ScenePlan p = GSON.fromJson(r, ScenePlan.class);
            return p != null ? p : new ScenePlan();
        }
    }

    public static void writeJson(Path path, Object obj) throws IOException {
        Files.createDirectories(path.getParent());
        try (Writer w = Files.newBufferedWriter(path)) {
            GSON.toJson(obj, w);
        }
    }
}
