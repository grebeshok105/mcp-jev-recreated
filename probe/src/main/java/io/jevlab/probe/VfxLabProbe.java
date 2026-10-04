package io.jevlab.probe;

import net.fabricmc.api.ModInitializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class VfxLabProbe implements ModInitializer {
    public static final String MOD_ID = "vfxlab-probe";
    public static final Logger LOGGER = LoggerFactory.getLogger("vfxlab-probe");

    @Override
    public void onInitialize() {
        LOGGER.info("vfxlab-probe initialized");
    }
}
