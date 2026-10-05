"""Scene lane: staged multi-resource playback inside the real client.

spec -> validate_scene -> compile_scene -> scene_plan.json -> probe
vfxlab.4_scene scenario -> frames + measurements.
"""
from .spec import SceneValidation, validate_scene
from .compile import compile_scene, write_plan, load_level_events

__all__ = [
    "SceneValidation",
    "validate_scene",
    "compile_scene",
    "write_plan",
    "load_level_events",
]
