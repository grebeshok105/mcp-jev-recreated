package io.jevlab.probe.mixin;

import it.unimi.dsi.fastutil.ints.Int2ObjectMap;
import java.util.Map;
import java.util.Queue;
import net.minecraft.client.particle.Particle;
import net.minecraft.client.particle.ParticleEngine;
import net.minecraft.client.particle.ParticleProvider;
import net.minecraft.client.particle.ParticleRenderType;
import net.minecraft.client.particle.TrackingEmitter;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
import org.spongepowered.asm.mixin.gen.Invoker;

@Mixin(ParticleEngine.class)
public interface ParticleEngineAccessor {
    @Accessor("particles")
    Map<ParticleRenderType, Queue<Particle>> vfxlab$getParticles();

    @Accessor("providers")
    Int2ObjectMap<ParticleProvider<?>> vfxlab$getProviders();

    @Accessor("trackingEmitters")
    Queue<TrackingEmitter> vfxlab$getTrackingEmitters();

    @Invoker("clearParticles")
    void vfxlab$clearParticles();
}
