"""角色、目标和生命周期等实体运行态状态。"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from genshin_sim.core.entity_states.characters import CharacterRuntimeState
    from genshin_sim.core.entity_states.lifecycle import EntityLifecycle, EntityLifecycleState
    from genshin_sim.core.entity_states.targets import TargetRuntimeCollection, TargetRuntimeState

__all__ = [
    "CharacterRuntimeState",
    "EntityLifecycle",
    "EntityLifecycleState",
    "TargetRuntimeCollection",
    "TargetRuntimeState",
]

_EXPORT_MODULES = {
    "CharacterRuntimeState": "genshin_sim.core.entity_states.characters",
    "EntityLifecycle": "genshin_sim.core.entity_states.lifecycle",
    "EntityLifecycleState": "genshin_sim.core.entity_states.lifecycle",
    "TargetRuntimeCollection": "genshin_sim.core.entity_states.targets",
    "TargetRuntimeState": "genshin_sim.core.entity_states.targets",
}


def __getattr__(name: str) -> object:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
