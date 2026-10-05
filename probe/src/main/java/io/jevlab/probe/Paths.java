package io.jevlab.probe;

import java.nio.file.Path;
import net.fabricmc.loader.api.FabricLoader;

/** Output locations for probe artifacts. */
public final class Paths {
    private Paths() {}

    /** Root output directory: -Dvfxlab.outdir, default <gameDir>/vfxlab. */
    public static Path outDir() {
        String prop = System.getProperty("vfxlab.outdir");
        if (prop != null && !prop.isBlank()) {
            return Path.of(prop);
        }
        return FabricLoader.getInstance().getGameDir().resolve("vfxlab");
    }

    public static Path capturePlanFile() {
        return outDir().resolve("capture_plan.json");
    }

    public static Path dumpDir() {
        return outDir().resolve("dump");
    }

    public static Path framesDir() {
        return outDir().resolve("frames");
    }

    public static Path measurementsDir() {
        return outDir().resolve("measurements");
    }

    public static Path fixturesDir() {
        String prop = System.getProperty("vfxlab.fixturesdir");
        if (prop != null && !prop.isBlank()) {
            return Path.of(prop);
        }
        return outDir().resolve("fixtures");
    }

    public static Path sceneDir() {
        return outDir().resolve("scene");
    }

    public static Path sceneFile() {
        return sceneDir().resolve("scene_plan.json");
    }

    public static Path sceneResultsFile() {
        return sceneDir().resolve("scene_results.json");
    }

    public static Path diagnosticsFile() {
        return outDir().resolve("probe_diagnostics.json");
    }
}
