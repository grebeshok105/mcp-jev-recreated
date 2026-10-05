package io.jevlab.probe.uitest;

import com.lowdragmc.lowdraglib2.registry.RegistrationEnvironment;
import com.lowdragmc.lowdraglib2.registry.annotation.LDLRegisterClient;
import com.lowdragmc.lowdraglib2.uitest.ScenarioBuilder;
import com.lowdragmc.lowdraglib2.uitest.ScenarioOptions;
import com.lowdragmc.lowdraglib2.uitest.UIScenario;

/**
 * Scene playback lane: replays a timed multi-resource scene plan
 * (`<out>/scene/scene_plan.json`) inside the real client. Fourth in the
 * vfxlab group; runs standalone via
 * {@code -Dldlib2.uitest.run=vfxlab.4_scene} (or the
 * {@code -Pvfxlab.uitestSelection} gradle property).
 */
@LDLRegisterClient(
        name = "vfxlab.4_scene",
        group = "vfxlab",
        registry = UIScenario.REGISTRY,
        environment = RegistrationEnvironment.DEV_ONLY,
        priority = 40)
public final class SceneScenario implements UIScenario {
    private final SceneRun run = new SceneRun();

    @Override
    public void configure(ScenarioOptions options) {
        // SceneRun computes a tighter bound from plan.duration x angles;
        // this budget covers the maximum sane scene.
        options.scenarioTimeoutMs(600_000L);
    }

    @Override
    public void define(ScenarioBuilder builder) {
        run.define(builder);
    }
}
