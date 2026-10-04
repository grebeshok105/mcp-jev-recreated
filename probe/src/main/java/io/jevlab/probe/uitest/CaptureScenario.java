package io.jevlab.probe.uitest;

import com.lowdragmc.lowdraglib2.registry.RegistrationEnvironment;
import com.lowdragmc.lowdraglib2.registry.annotation.LDLRegisterClient;
import com.lowdragmc.lowdraglib2.uitest.ScenarioBuilder;
import com.lowdragmc.lowdraglib2.uitest.ScenarioOptions;
import com.lowdragmc.lowdraglib2.uitest.UIScenario;

/**
 * Drives the plan-based frame/measurement capture. Runs under the ldlib2 UITestRunner
 * when the client is launched with {@code -Dldlib2.uitest.run=vfxlab*}; third in the
 * vfxlab group so the registry dump and .fx fixtures already exist on disk.
 */
@LDLRegisterClient(
        name = "vfxlab.3_capture",
        group = "vfxlab",
        registry = UIScenario.REGISTRY,
        environment = RegistrationEnvironment.DEV_ONLY,
        priority = 30)
public final class CaptureScenario implements UIScenario {
    private final CaptureRun run = new CaptureRun();

    @Override
    public void configure(ScenarioOptions options) {
        // a full-catalog sweep (197 shots x angles x ticks) needs far more
        // than the default 120s scenario budget
        options.scenarioTimeoutMs(5_400_000L);
    }

    @Override
    public void define(ScenarioBuilder builder) {
        run.define(builder);
    }
}
