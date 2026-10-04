package io.jevlab.probe.uitest;

import com.lowdragmc.lowdraglib2.registry.RegistrationEnvironment;
import com.lowdragmc.lowdraglib2.registry.annotation.LDLRegisterClient;
import com.lowdragmc.lowdraglib2.uitest.ScenarioBuilder;
import com.lowdragmc.lowdraglib2.uitest.UIScenario;
import io.jevlab.probe.Paths;
import io.jevlab.probe.fx.FxFixtureFactory;

import java.util.ArrayList;
import java.util.List;

/**
 * Generates the real .fx fixture files used as capture subjects, via Photon's own
 * serialization path. Second in the vfxlab group (after the dump, before capture).
 */
@LDLRegisterClient(
        name = "vfxlab.2_fixturegen",
        group = "vfxlab",
        registry = UIScenario.REGISTRY,
        environment = RegistrationEnvironment.DEV_ONLY,
        priority = 20)
public final class FixtureGenScenario implements UIScenario {
    @Override
    public void define(ScenarioBuilder builder) {
        builder.step("vfxlab:fixturegen", ctx -> {
            List<String> diagnostics = new ArrayList<>();
            try {
                FxFixtureFactory.buildAll(Paths.fixturesDir());
                // also drop a copy into ldlib2's hidden-pack path so FXHelper can
                // resolve vfxlab:* fx ids at capture time
                java.nio.file.Path hidden = net.fabricmc.loader.api.FabricLoader.getInstance()
                        .getGameDir().resolve("ldlib2").resolve("assets")
                        .resolve("vfxlab").resolve("fx");
                FxFixtureFactory.buildAll(hidden);
            } catch (Throwable t) {
                diagnostics.add("fixture generation failed: " + t);
            }
            if (!diagnostics.isEmpty()) {
                try {
                    io.jevlab.probe.capture.CapturePlan.writeJson(Paths.diagnosticsFile(), diagnostics);
                } catch (java.io.IOException ignored) {
                }
            }
        });
        builder.ticks(5);
    }
}
