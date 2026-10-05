package io.jevlab.probe.capture;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * JSON-driven capture plan. One plan = one capture batch.
 *
 * <pre>{@code
 * {
 *   "version": 1,
 *   "scene": {"pos": [8.5, 6.0, 8.5], "time": 6000, "weather": "clear"},
 *   "defaults": {"frames": [2, 5, 10, 20, 40], "angles": ["front","side","top","threequarter"]},
 *   "shots": [
 *     {"id": "minecraft:sonic_boom", "kind": "particle", "options": {}},
 *     {"id": "levelevent:2001", "kind": "level_event", "event": 2001, "data_block": "minecraft:stone"},
 *     {"id": "vfxlab_probe:test_ring", "kind": "fx"},
 *     {"id": "superheroes:homelander_clap_flash", "kind": "quasar_emitter"}
 *   ]
 * }
 * }</pre>
 */
public final class CapturePlan {
    public int version = 1;
    public Scene scene = new Scene();
    public Defaults defaults = new Defaults();
    public List<Shot> shots = new ArrayList<>();

    public static final class Scene {
        public double[] pos = {8.5, 6.0, 8.5};
        public int time = 6000;
        public String weather = "clear";
    }

    public static final class Defaults {
        public int[] frames = {2, 5, 10, 20, 40};
        public String[] angles = {"front", "side", "top", "threequarter"};
        /** observation horizon when a shot lists no explicit frames */
        public int max_ticks = 60;
    }

    public static final class Shot {
        public String id;
        /** original resource id when `id` is a synthetic shot id
         *  (e.g. a world_event compiled to a level_event shot) —
         *  set by the scene compiler so results can index the resource
         *  the caller actually asked for */
        public String resource_id;
        public String kind; // particle | level_event | fx | quasar_emitter
        /** extra particle options spec, e.g. {"color":[1,0,0],"scale":1.0} or {"block":"minecraft:stone"} */
        public JsonObject options;
        /** /particle-style arguments appended after the id (for parameterized types) */
        public String particle_args;
        /** level_event id when kind=level_event */
        public Integer event;
        /** level_event data: block id whose state id is passed as event data */
        public String data_block;
        /** level_event data: raw integer data (overrides data_block when set) */
        public Integer data_int;
        /** entity id to attach entity-scoped events (not used yet) */
        public int[] frames;
        public String[] angles;
        /** looping effects get destroyed after the last frame; default true for fx/emitter */
        public Boolean stop_after;
    }

    private static final Gson GSON = new Gson();

    public static CapturePlan load(Path file) throws IOException {
        try (Reader r = Files.newBufferedReader(file)) {
            CapturePlan plan = GSON.fromJson(r, CapturePlan.class);
            if (plan == null) {
                plan = new CapturePlan();
            }
            return plan;
        }
    }

    public static void writeJson(Path file, Object value) throws IOException {
        Files.createDirectories(file.getParent());
        try (Writer w = Files.newBufferedWriter(file)) {
            GSON.toJson(value, w);
        }
    }
}
