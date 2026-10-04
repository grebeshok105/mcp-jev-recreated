package io.jevlab.probe.uitest;

import com.lowdragmc.lowdraglib2.registry.RegistrationEnvironment;
import com.lowdragmc.lowdraglib2.registry.annotation.LDLRegisterClient;
import com.lowdragmc.lowdraglib2.uitest.ScenarioBuilder;
import com.lowdragmc.lowdraglib2.uitest.UIScenario;
import io.jevlab.probe.Paths;
import io.jevlab.probe.dump.RegistryDump;

import java.util.List;

/**
 * Dumps runtime registries (particle types, level events, particle providers, Photon
 * registries, resource index) to {@code <out>/dump/*.json}. First in the vfxlab group.
 */
@LDLRegisterClient(
        name = "vfxlab.1_dump",
        group = "vfxlab",
        registry = UIScenario.REGISTRY,
        environment = RegistrationEnvironment.DEV_ONLY,
        priority = 10)
public final class DumpScenario implements UIScenario {
    @Override
    public void define(ScenarioBuilder builder) {
        builder.step("vfxlab:dump", ctx -> {
            try {
                RegistryDump.dumpAll();
            } catch (Throwable t) {
                try {
                    io.jevlab.probe.capture.CapturePlan.writeJson(
                            Paths.diagnosticsFile(), List.of("registry dump failed: " + t));
                } catch (java.io.IOException ignored) {
                }
            }
        });
        // let the file writes settle before the next scenario starts
        builder.ticks(5);
    }
}
