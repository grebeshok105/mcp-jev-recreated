package io.jevlab.probe.capture;

import net.minecraft.client.particle.Particle;

/** Counts particles added to the engine while a capture window is active. */
public final class SpawnCounters {
    private static volatile boolean active;
    private static volatile int added;

    private SpawnCounters() {}

    public static void begin() {
        added = 0;
        active = true;
    }

    public static int stopAndGet() {
        active = false;
        return added;
    }

    public static void onParticleAdded(Particle particle) {
        if (active) {
            added++;
        }
    }

    public static boolean isActive() {
        return active;
    }
}
