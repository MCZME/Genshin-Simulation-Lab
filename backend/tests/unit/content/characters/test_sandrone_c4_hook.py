"""C4 协同攻击 hook 的单元测试：来源判定、触发档位、内置冷却与星烁组装。

数值全部为合成数据（见测试规范 §3.2）；辉映证据经星烁辉映证据窄端口
注入桩（hook 只打包攻击定义，攻击力由公式侧从面板读取，不在本层读取）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.hooks import (
    SandroneC4CoordinatedAttackHook,
)
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.systems.reaction.radiance import (
    RadianceEvidence,
    RadianceVariant,
)
from tests.helpers.events import make_damage_resolved_event

OWNER_REF = "character:slot_1"
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.sandrone.c4")


class _StubRadiancePort:
    """辉映证据端口桩：按构造参数返回固定档位系数。"""

    def __init__(self, *, conduct: float = 0.0, swirl: float = 0.0) -> None:
        self._conduct = conduct
        self._swirl = swirl

    def resolve(self, *, owner_ref: str, frame: int) -> RadianceEvidence | None:
        if self._conduct > 0.0:
            return RadianceEvidence(RadianceVariant.CONDUCT, self._conduct)
        if self._swirl > 0.0:
            return RadianceEvidence(RadianceVariant.SWIRL, self._swirl)
        return None

    def variant_multiplier(self, *, owner_ref: str, variant: RadianceVariant, frame: int) -> float:
        return self._conduct if variant is RadianceVariant.CONDUCT else self._swirl


def _context(
    *,
    conduct_multiplier: float = 0.0,
    swirl_multiplier: float = 0.0,
) -> SimulationContext:
    context = SimulationContext()
    context.register_system(_StubRadiancePort(conduct=conduct_multiplier, swirl=swirl_multiplier))
    return context


def _c4_event(
    frame: int,
    *,
    tag: str = "星超导冰",
    target: str = "target:1",
    source: str = OWNER_REF,
):
    return make_damage_resolved_event(
        frame,
        f"damage:{frame}",
        source_key=source,
        target_key=target,
        main_attack_tag=tag,
    )


def _c4_hook() -> SandroneC4CoordinatedAttackHook:
    return SandroneC4CoordinatedAttackHook(
        owner_ref=OWNER_REF,
        slot=1,
        attack_ratio=1.25,
        swirl_ratio=1.875,
        cooldown_frames=240,
    )


def test_c4_hook_procs_on_stellar_conduct_hit_with_cooldown():
    hook = _c4_hook()
    context = SimpleNamespace(simulation=_context())

    first = hook.handle(_c4_event(128), context)
    assert first.impact_requests, "首次星超导冰命中应触发协同攻击"
    request = cast(ImpactRequest, first.impact_requests[0])
    assert request.kind is ImpactKind.DAMAGE
    assert request.target_refs == ("target:1",)
    spec = request.damage_spec
    assert spec is not None and spec.main_attack_tag == "星超导冰"
    stellar = spec.stellar_reaction
    assert stellar is not None
    # 倍率与属性分开承载（D-082）：系数 = 星超导档位倍率，属性 = 攻击力。
    assert spec.scaling_terms[0].coefficient == pytest.approx(1.25)
    assert spec.scaling_terms[0].attribute_key == STAT_ATK_TOTAL
    # 无任何辉映证据时星烁基础系数保守回落 1.0。
    assert stellar.stellar_base_multiplier == pytest.approx(1.0)
    # P6 基础增伤与 C6 擢升由 provider 词条在结算期叠加（D-082），
    # 星烁输入基线保持缺省。
    assert stellar.stellar_base_bonus == pytest.approx(0.0)
    assert stellar.stellar_ascension_bonus == pytest.approx(0.0)

    # 冷却窗口内的星超导冰命中不重复触发；窗口外恢复。
    assert hook.handle(_c4_event(200), context).impact_requests == ()
    second = hook.handle(_c4_event(369), context)
    assert second.impact_requests


def test_c4_hook_switches_variant_on_stellar_swirl_hit():
    # 官方文本要求"视为对应星烁反应造成的伤害"：产出标签紧跟触发标签换成
    # 星扩散冰，倍率取星扩散档，星烁基础系数也取星扩散变体载荷（即使同时
    # 持有星超导证据也不串档）。
    hook = _c4_hook()
    context = SimpleNamespace(simulation=_context(conduct_multiplier=1.55, swirl_multiplier=1.0))

    procs = hook.handle(_c4_event(128, tag="星扩散冰"), context)
    assert procs.impact_requests, "星扩散冰命中应触发协同攻击"
    spec = cast(ImpactRequest, procs.impact_requests[0]).damage_spec
    assert spec is not None and spec.main_attack_tag == "星扩散冰"
    stellar = spec.stellar_reaction
    assert stellar is not None
    assert spec.scaling_terms[0].coefficient == pytest.approx(1.875)
    assert stellar.stellar_base_multiplier == pytest.approx(1.0)

    # 星超导冰与星扩散冰共用同一条内置冷却。
    assert hook.handle(_c4_event(200), context).impact_requests == ()
    assert hook.handle(_c4_event(369, tag="星扩散冰"), context).impact_requests


def test_c4_hook_ignores_hits_from_other_characters():
    # 先判来源：C4 文本限定"桑多涅的星超导/星扩散反应伤害"，队伍其他角色的
    # 同名标签伤害事实不触发。
    hook = _c4_hook()
    context = SimpleNamespace(simulation=_context(conduct_multiplier=1.55))
    assert hook.handle(_c4_event(10, source="character:slot_2"), context).impact_requests == ()
    assert (
        hook.handle(
            _c4_event(10, tag="星扩散冰", source="character:slot_2"), context
        ).impact_requests
        == ()
    )
    assert hook.last_proc_frame is None


def test_c4_hook_ignores_non_stellar_and_non_enemy_hits():
    hook = _c4_hook()
    context = SimpleNamespace(simulation=_context())
    assert hook.handle(_c4_event(10, tag="重击"), context).impact_requests == ()
    # 非冰系的星烁标签不在触发集合内。
    assert hook.handle(_c4_event(10, tag="星超导雷"), context).impact_requests == ()
    assert hook.handle(_c4_event(10, tag="星扩散风"), context).impact_requests == ()
    character_hit = make_damage_resolved_event(
        10,
        "damage:10",
        source_key=OWNER_REF,
        target_key="character:slot_2",
        main_attack_tag="星超导冰",
    )
    assert hook.handle(character_hit, context).impact_requests == ()
    assert hook.last_proc_frame is None
