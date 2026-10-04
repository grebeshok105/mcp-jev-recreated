package io.jevlab.probe.capture;

import io.jevlab.probe.mixin.ParticleEngineAccessor;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import net.minecraft.client.Minecraft;
import net.minecraft.client.particle.Particle;
import net.minecraft.client.particle.ParticleRenderType;

/** Per-tick sampling of the live particle engine during a capture window. */
public final class Measurer {
    private final List<TickSample> samples = new ArrayList<>();
    private final String resourceId;
    private int tick;
    private int totalSpawned;

    public static final class TickSample {
        public int tick;
        public int alive;
        public int spawned_total;
        public Map<String, Integer> by_render_type = new HashMap<>();
        public float[] bounds_min;
        public float[] bounds_max;
    }

    public Measurer(String resourceId) {
        this.resourceId = resourceId;
    }

    public void begin() {
        samples.clear();
        tick = 0;
        SpawnCounters.begin();
    }

    /** Call once per client tick while the capture window is open. */
    public void sampleTick() {
        Minecraft mc = Minecraft.getInstance();
        TickSample s = new TickSample();
        s.tick = tick++;
        Map<ParticleRenderType, Queue<Particle>> queues =
                ((ParticleEngineAccessor) mc.particleEngine).vfxlab$getParticles();
        float[] min = {Float.MAX_VALUE, Float.MAX_VALUE, Float.MAX_VALUE};
        float[] max = {-Float.MAX_VALUE, -Float.MAX_VALUE, -Float.MAX_VALUE};
        int alive = 0;
        for (Map.Entry<ParticleRenderType, Queue<Particle>> e : queues.entrySet()) {
            Queue<Particle> q = e.getValue();
            if (q == null) continue;
            int n = q.size();
            alive += n;
            if (n > 0) {
                s.by_render_type.put(String.valueOf(e.getKey()), n);
                for (Particle p : q) {
                    net.minecraft.world.phys.AABB bb = p.getBoundingBox();
                    if (bb == null) continue;
                    min[0] = Math.min(min[0], (float) bb.minX);
                    min[1] = Math.min(min[1], (float) bb.minY);
                    min[2] = Math.min(min[2], (float) bb.minZ);
                    max[0] = Math.max(max[0], (float) bb.maxX);
                    max[1] = Math.max(max[1], (float) bb.maxY);
                    max[2] = Math.max(max[2], (float) bb.maxZ);
                }
            }
        }
        s.alive = alive;
        if (alive > 0) {
            s.bounds_min = min;
            s.bounds_max = max;
        }
        samples.add(s);
    }

    /** Finish the window; returns a serializable result map. */
    public Map<String, Object> finish() {
        totalSpawned = SpawnCounters.stopAndGet();
        int peak = samples.stream().mapToInt(s -> s.alive).max().orElse(0);
        int lastAlive = samples.isEmpty() ? 0 : samples.get(samples.size() - 1).alive;
        int firstVisible = -1;
        for (TickSample s : samples) {
            if (s.alive > 0) {
                firstVisible = s.tick;
                break;
            }
        }
        float[] unionMin = null, unionMax = null;
        for (TickSample s : samples) {
            if (s.bounds_min == null) continue;
            if (unionMin == null) {
                unionMin = s.bounds_min.clone();
                unionMax = s.bounds_max.clone();
            } else {
                for (int i = 0; i < 3; i++) {
                    unionMin[i] = Math.min(unionMin[i], s.bounds_min[i]);
                    unionMax[i] = Math.max(unionMax[i], s.bounds_max[i]);
                }
            }
        }
        Map<String, Object> out = new HashMap<>();
        out.put("id", resourceId);
        out.put("total_spawned", totalSpawned);
        out.put("peak_alive", peak);
        out.put("alive_at_end", lastAlive);
        out.put("first_visible_tick", firstVisible);
        out.put("ticks", samples.size());
        out.put("samples", samples);
        if (unionMin != null) {
            out.put("bounds_min", unionMin);
            out.put("bounds_max", unionMax);
        }
        return out;
    }
}
