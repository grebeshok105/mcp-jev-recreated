package io.jevlab.probe.fx;

import com.lowdragmc.lowdraglib2.Platform;
import com.lowdragmc.photon.client.fx.FX;
import com.lowdragmc.photon.client.gameobject.emitter.beam.BeamEmitter;
import com.lowdragmc.photon.client.gameobject.emitter.data.EmissionSetting;
import com.lowdragmc.photon.client.gameobject.emitter.data.number.NumberFunction;
import com.lowdragmc.photon.client.gameobject.emitter.data.shape.Circle;
import com.lowdragmc.photon.client.gameobject.emitter.data.shape.Cone;
import com.lowdragmc.photon.client.gameobject.emitter.data.shape.Sphere;
import com.lowdragmc.photon.client.gameobject.emitter.particle.ParticleEmitter;
import com.lowdragmc.photon.client.gameobject.emitter.trail.TrailEmitter;
import com.lowdragmc.photon.gui.editor.FXProject;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtIo;
import org.joml.Vector3f;

/**
 * Programmatically builds visually distinct FX fixtures through Photon's own
 * emitter classes and serializes them as real {@code .fx} files (gzip NBT —
 * exactly what the in-game editor's export writes).
 */
public final class FxFixtureFactory {
    private FxFixtureFactory() {}

    public record BuiltFixture(String id, String description, Path file) {}

    /** Build every fixture into {@code dir}. */
    public static List<BuiltFixture> buildAll(Path dir) throws IOException {
        Files.createDirectories(dir);
        List<BuiltFixture> out = new ArrayList<>();
        out.add(write(dir, "ember_ring_burst", "one-shot radial ring of fire embers", ringBurstFx()));
        out.add(write(dir, "smoke_plume", "looping upward smoke plume column", smokePlumeFx()));
        out.add(write(dir, "laser_beam", "thin straight energy beam segment", laserBeamFx()));
        out.add(write(dir, "ribbon_trail", "looping ribbon trail", ribbonTrailFx()));
        out.add(write(dir, "sparkle_sphere", "looping sphere of small drifting sparks", sparkleSphereFx()));
        return out;
    }

    private static EmissionSetting.Burst burst(int time, int count) {
        EmissionSetting.Burst b = new EmissionSetting.Burst();
        b.time = time;
        b.setCount(NumberFunction.constant(count));
        b.cycles = 1;
        b.interval = 0;
        b.probability = 1f;
        return b;
    }

    private static FX ringBurstFx() {
        ParticleEmitter emitter = new ParticleEmitter();
        emitter.config.setLooping(false);
        emitter.config.setDuration(30);
        emitter.config.setStartLifetime(NumberFunction.constant(45));
        emitter.config.setStartSpeed(NumberFunction.constant(0.8f));
        emitter.config.setStartColor(NumberFunction.color(0xFFFF5522));
        emitter.config.emission.getBursts().add(burst(0, 60));
        Circle circle = new Circle();
        circle.setRadius(0.15f);
        emitter.config.shape.setShape(circle);
        FX fx = new FX();
        fx.getFxData().objects().add(emitter);
        return fx;
    }

    private static FX smokePlumeFx() {
        ParticleEmitter emitter = new ParticleEmitter();
        emitter.config.setLooping(true);
        emitter.config.setDuration(200);
        emitter.config.setStartLifetime(NumberFunction.constant(80));
        emitter.config.setStartSpeed(NumberFunction.constant(0.45f));
        emitter.config.setStartColor(NumberFunction.color(0x99AAAAAA));
        emitter.config.emission.setEmissionRate(NumberFunction.constant(12));
        Cone cone = new Cone();
        cone.setRadius(0.3f);
        emitter.config.shape.setShape(cone);
        FX fx = new FX();
        fx.getFxData().objects().add(emitter);
        return fx;
    }

    private static FX sparkleSphereFx() {
        ParticleEmitter emitter = new ParticleEmitter();
        emitter.config.setLooping(true);
        emitter.config.setDuration(160);
        emitter.config.setStartLifetime(NumberFunction.constant(50));
        emitter.config.setStartSpeed(NumberFunction.constant(0.3f));
        emitter.config.setStartColor(NumberFunction.color(0xFF88CCFF));
        emitter.config.emission.setEmissionRate(NumberFunction.constant(20));
        Sphere sphere = new Sphere();
        sphere.setRadius(0.4f);
        emitter.config.shape.setShape(sphere);
        FX fx = new FX();
        fx.getFxData().objects().add(emitter);
        return fx;
    }

    private static FX laserBeamFx() {
        BeamEmitter beam = new BeamEmitter();
        beam.getConfig().setLooping(true);
        beam.getConfig().setDuration(120);
        // end is relative to the emitter origin: +x keeps the beam inside the
        // capture frame for front/side cameras; pointing +z would shoot it into
        // the camera itself
        beam.getConfig().getEnd().set(new Vector3f(4, 0.5f, 0));
        beam.getConfig().setWidth(NumberFunction.constant(0.12f));
        beam.getConfig().setEmitRate(NumberFunction.constant(30));
        beam.getConfig().setColor(NumberFunction.color(0xFF33CCFF));
        FX fx = new FX();
        fx.getFxData().objects().add(beam);
        return fx;
    }

    private static FX ribbonTrailFx() {
        TrailEmitter trail = new TrailEmitter();
        trail.config.setLooping(true);
        trail.config.setDuration(160);
        trail.config.setTime(40);
        trail.config.setWidthOverTrail(NumberFunction.constant(0.25f));
        FX fx = new FX();
        fx.getFxData().objects().add(trail);
        return fx;
    }

    private static BuiltFixture write(Path dir, String name, String description, FX fx) throws IOException {
        CompoundTag tag = fx.serializeNBT(Platform.getFrozenRegistry());
        tag.putInt("version", FXProject.VERSION);
        Path file = dir.resolve(name + ".fx");
        NbtIo.writeCompressed(tag, file);
        return new BuiltFixture("vfxlab_probe:" + name, description, file);
    }
}
