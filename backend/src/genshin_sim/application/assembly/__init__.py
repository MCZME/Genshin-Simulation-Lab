"""基于配置、资产和内容 handler 的仿真组装。"""

from genshin_sim.application.assembly.assembler import SimulationAssembler
from genshin_sim.application.assembly.attributes import AttributeRuntimeBundle
from genshin_sim.application.assembly.errors import (
    AssemblyError,
    InvalidRuntimePayloadError,
    MissingRuntimeAssetError,
    MissingRuntimeHandlerError,
)
from genshin_sim.application.assembly.models import (
    AssembledSimulation,
    RuntimeAssetBundle,
    RuntimeContentBundle,
)
from genshin_sim.application.assembly.reaction_capabilities import (
    StaticReactionEligibilityPort,
    build_static_reaction_eligibility_port,
)
from genshin_sim.application.assembly.stages import (
    AssetBundleLoader,
    ConfigTranslator,
    ContentCompiler,
    RuntimeAssembler,
)

__all__ = [
    "AssembledSimulation",
    "AssetBundleLoader",
    "AssemblyError",
    "AttributeRuntimeBundle",
    "ConfigTranslator",
    "ContentCompiler",
    "InvalidRuntimePayloadError",
    "MissingRuntimeAssetError",
    "MissingRuntimeHandlerError",
    "RuntimeAssembler",
    "RuntimeAssetBundle",
    "RuntimeContentBundle",
    "SimulationAssembler",
    "StaticReactionEligibilityPort",
    "build_static_reaction_eligibility_port",
]
