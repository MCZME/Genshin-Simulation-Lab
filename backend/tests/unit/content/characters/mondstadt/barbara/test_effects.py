"""芭芭拉安可被动效果内容单元。"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara import (
    BARBARA_ENCORE_EFFECT_HANDLER_KEY,
    create_barbara_encore_effect,
)
from genshin_sim.content.characters.mondstadt.barbara.hooks import (
    BarbaraRingEncoreHook,
)
from genshin_sim.content.definitions.effects import EffectKind, UnlockKind
from tests.helpers import barbara as barbara_helpers


def test_barbara_encore_effect_compiles_effect_payload_into_hook():
    # 与集成（tests/integration/content/barbara/test_passives.py::
    # test_barbara_encore_effect_mounts_hook_from_effect_payload）共存；
    # 本用例只锁定效果 payload 到 hook 的编译规格，挂载与延长行为由集成用例锁定。
    unit = create_barbara_encore_effect(barbara_helpers.encore_request())

    assert unit.handler_key == BARBARA_ENCORE_EFFECT_HANDLER_KEY
    assert unit.slot == 1
    assert len(unit.event_hooks) == 1
    hook = unit.event_hooks[0]
    assert isinstance(hook, BarbaraRingEncoreHook)
    assert hook.hook_key == "barbara.encore:character:slot_1"
    assert hook.subscriptions == ("ENERGY_PICKUP_SETTLED",)
    assert len(unit.effects) == 1
    effect = unit.effects[0]
    assert effect.effect_key == "character:10000014:passive:5"
    assert effect.kind is EffectKind.PASSIVE
    assert effect.unlock.kind is UnlockKind.ASCENSION
    assert effect.unlock.threshold == 4
    assert effect.component is not None
    assert effect.component.kind == "extend_created_object_on_energy_pickup"
    assert effect.component.params["extend_frames"] == 60
    assert effect.component.params["max_extra_frames"] == 300
    assert effect.component.params["object_key"] == "barbara.ring"
