package io.jevlab.probe.mixin;

import io.jevlab.probe.capture.SpawnCounters;
import net.minecraft.client.particle.Particle;
import net.minecraft.client.particle.ParticleEngine;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(ParticleEngine.class)
public class ParticleEngineSpawnCounter {
    @Inject(method = "add", at = @At("HEAD"))
    private void vfxlab$countAdd(Particle particle, CallbackInfo ci) {
        SpawnCounters.onParticleAdded(particle);
    }
}
