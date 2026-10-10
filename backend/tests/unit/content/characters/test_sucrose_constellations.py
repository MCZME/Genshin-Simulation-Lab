"""砂糖命座 C1–C6 的单元测试：静态切片取值、命座单元形态与两个 hook 的判据。

数值全部为合成数据（见测试规范 §3.2）：真实资产效果行的正确性由资产构建与
校验链路承担，这里只锁定
「资产效果行 -> 命座工厂 -> 编译参数 / 天赋等级提升 / hook / Buff 定义」、
「C1 / C2 的静态切片随命座取值」与
「C4 计次与随机减冷却、C6 染色触发与投放范围」三条接线。

C4 的减冷却是**运行期**行为（随机值只能在触发帧决定），走本次新增的内容侧
冷却意图通道（``HookResult.cooldown_requests``），因此这里也锁定
「计次满 7 -> 产出 CooldownMutationBatchRequest -> 计数清零」这条链路。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from genshin_sim.content.characters.mondstadt.sucrose.content import (
    create_sucrose_content_unit,
)
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ASSET_KEY,
    SUCROSE_C6_BUFF_DEFINITION_KEY,
    SUCROSE_C6_DAMAGE_BONUS,
    SUCROSE_C6_MAGE_ENHANCEMENT_BONUS,
    SUCROSE_C6_MAGE_ENHANCEMENT_BUFF_DEFINITION_KEY,
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C1_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C2_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C3_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C4_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C5_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
    SUCROSE_SPIRIT_ABSORBED_TICK_IMPACT_KEY,
    SUCROSE_SPIRIT_DURATION_FRAMES,
    SUCROSE_SPIRIT_TICK_COUNT,
)
from genshin_sim.content.characters.mondstadt.sucrose.effects import (
    create_sucrose_constellation_c1,
    create_sucrose_constellation_c2,
    create_sucrose_constellation_c3,
    create_sucrose_constellation_c4,
    create_sucrose_constellation_c5,
    create_sucrose_constellation_c6,
)
from genshin_sim.content.characters.mondstadt.sucrose.hooks import (
    SucroseC4HitCounterHook,
    SucroseC6AbsorbedBonusHook,
)
from genshin_sim.content.characters.mondstadt.sucrose.modifiers import (
    MAGE_ENHANCEMENT_ELEMENTS,
    build_c6_damage_bonus_buff_definition,
    c6_damage_bonus_modifier_values,
    c6_damage_bonus_term_key,
    mage_enhancement_modifier_values,
    mage_enhancement_term_key,
)
from genshin_sim.content.characters.mondstadt.sucrose.spirit import resolve_spirit_timing
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.definitions.effects import EffectKind, UnlockKind
from genshin_sim.content.hooks import HookContext
from genshin_sim.content.registries import (
    CharacterContentUnitRequest,
    EffectContentUnitRequest,
)
from genshin_sim.content.team.mage import MageRoster
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import Element
from genshin_sim.core.entity_states import CharacterRuntimeState
from genshin_sim.core.events import EventType
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.simulation.random_source import RandomSource
from genshin_sim.core.systems.cooldown import (
    CooldownMutationBatchRequest,
    CooldownRecoveryMode,
    ReduceRemainingCooldownRequest,
)
from tests.helpers import sucrose as sucrose_helpers

FRAME = 100
OWNER_REF = "character:slot_1"
SLOT_1 = AttributeSubjectRef.character("character:slot_1")
SLOT_2 = AttributeSubjectRef.character("character:slot_2")
SLOT_3 = AttributeSubjectRef.character("character:slot_3")
_C1_KEY = SUCROSE_CONSTELLATION_C1_HANDLER_KEY
_C2_KEY = SUCROSE_CONSTELLATION_C2_HANDLER_KEY
_C3_KEY = SUCROSE_CONSTELLATION_C3_HANDLER_KEY
_C4_KEY = SUCROSE_CONSTELLATION_C4_HANDLER_KEY
_C5_KEY = SUCROSE_CONSTELLATION_C5_HANDLER_KEY
_C6_KEY = SUCROSE_CONSTELLATION_C6_HANDLER_KEY

# 真实资产各层的分量形状（数值为合成值）。
_C1_COMPONENTS = (1.0,)
_C2_COMPONENTS = (2.0,)
_C3_COMPONENTS = (3.0, 15.0)
_C4_COMPONENTS = (7.0, 1.0, -7.0, 0.1)
_C5_COMPONENTS = (3.0, 15.0)
_C6_COMPONENTS = (0.2,)


def _effect_params(values: tuple[float, ...]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "合成命座行",
        "components": [
            {"kind": "numeric", "format": "number", "values": [value]} for value in values
        ],
    }


def _request(
    params: dict[str, object],
    *,
    handler_key: str,
    unlock_key: str,
    slot: int | None = 1,
    constellation: int = 0,
    owner_key: str = SUCROSE_ASSET_KEY,
) -> EffectContentUnitRequest:
    unit_request = EffectContentUnitRequest(
        handler_key=handler_key,
        effect_key=f"{SUCROSE_ASSET_KEY}:constellation:{unlock_key}",
        effect_kind="constellation",
        owner_type="character",
        owner_key=owner_key,
        slot=slot,
        params=params,
        unlock_key=unlock_key,
    )
    # 命座单元按归属上下文里的命座数决定 C6 的时长（C2 延长后为 8s）。
    object.__setattr__(
        unit_request.owner_context,
        "constellation",
        constellation,
    )
    return unit_request


def _c1_request(
    values: tuple[float, ...] = _C1_COMPONENTS, **overrides: Any
) -> EffectContentUnitRequest:
    kwargs: dict[str, Any] = {
        "handler_key": _C1_KEY,
        "unlock_key": "c1",
    }
    kwargs.update(overrides)
    return _request(_effect_params(values), **kwargs)


def _c2_request(
    values: tuple[float, ...] = _C2_COMPONENTS, **overrides: Any
) -> EffectContentUnitRequest:
    kwargs: dict[str, Any] = {"handler_key": _C2_KEY, "unlock_key": "c2"}
    kwargs.update(overrides)
    return _request(_effect_params(values), **kwargs)


def _c3_request(
    values: tuple[float, ...] = _C3_COMPONENTS, **overrides: Any
) -> EffectContentUnitRequest:
    kwargs: dict[str, Any] = {"handler_key": _C3_KEY, "unlock_key": "c3"}
    kwargs.update(overrides)
    return _request(_effect_params(values), **kwargs)


def _c4_request(
    values: tuple[float, ...] = _C4_COMPONENTS, **overrides: Any
) -> EffectContentUnitRequest:
    kwargs: dict[str, Any] = {"handler_key": _C4_KEY, "unlock_key": "c4"}
    kwargs.update(overrides)
    return _request(_effect_params(values), **kwargs)


def _c5_request(
    values: tuple[float, ...] = _C5_COMPONENTS, **overrides: Any
) -> EffectContentUnitRequest:
    kwargs: dict[str, Any] = {"handler_key": _C5_KEY, "unlock_key": "c5"}
    kwargs.update(overrides)
    return _request(_effect_params(values), **kwargs)


def _c6_request(
    values: tuple[float, ...] = _C6_COMPONENTS, **overrides: Any
) -> EffectContentUnitRequest:
    kwargs: dict[str, Any] = {"handler_key": _C6_KEY, "unlock_key": "c6"}
    kwargs.update(overrides)
    return _request(_effect_params(values), **kwargs)


def _team(slots: tuple[int, ...]) -> TeamRuntimeState:
    return TeamRuntimeState(
        tuple(
            CharacterRuntimeState(slot=slot, character_key=f"character:fixture_{slot}", level=90)
            for slot in slots
        )
    )


def _context(
    *,
    team_slots: tuple[int, ...] = (1, 2, 3),
    mage_slots: tuple[int, ...] | None = None,
    seed: int | None = None,
) -> HookContext:
    simulation = SimulationContext()
    if mage_slots is not None:
        simulation.register_system(MageRoster(mage_slots))
    if seed is not None:
        simulation.random_source = RandomSource(seed)
    return HookContext(frame=FRAME, round=0, simulation=simulation, states=_team(team_slots))


def _damage_event(
    *,
    frame: int = FRAME,
    tag: str = "普通攻击1",
    request_id: str = "impact:sucrose.normal_attack_1:damage",
    source: AttributeSubjectRef = SLOT_1,
    element: Element = Element.ANEMO,
    target_id: str = "target:1",
) -> SimpleNamespace:
    """伤害结算事实替身（只有 hook 实际读取的字段）。"""

    return SimpleNamespace(
        event_type=EventType.DAMAGE_RESOLVED,
        frame=frame,
        payload=SimpleNamespace(
            result=SimpleNamespace(
                request_id=request_id,
                main_attack_tag=tag,
                source_ref=source,
                target_ref=AttributeSubjectRef.target(target_id),
                element=element,
            )
        ),
    )


# --- C1 / C2：静态切片的取值 ------------------------------------------------


def test_resolve_spirit_timing_derives_window_duration_and_ticks():
    assert resolve_spirit_timing(0) == (360, 361, 3)
    # C2：窗口 6s → 8s，拍数 3 → 4（137 / 257 / 377 / 497）。
    assert resolve_spirit_timing(2) == (480, 481, 4)


def test_resolve_spirit_timing_rejects_negative_extra_seconds():
    with pytest.raises(ContentUnitValidationError):
        resolve_spirit_timing(-1)


def test_c1_unit_records_extra_charge_from_asset_row():
    unit = create_sucrose_constellation_c1(_c1_request())

    assert unit.handler_key == _C1_KEY
    assert unit.effects[0].kind is EffectKind.CONSTELLATION
    assert unit.effects[0].unlock.kind is UnlockKind.CONSTELLATION
    assert unit.effects[0].unlock.threshold == 1
    assert unit.compiled_params["extra_charges"] == 1
    # 充能数不落在效果单元上：那是冷却定义的静态切片（由角色单元按命座产出）。
    assert unit.cooldown_definitions == ()


def test_c2_unit_records_window_derivation():
    unit = create_sucrose_constellation_c2(_c2_request())

    assert unit.effects[0].unlock.threshold == 2
    assert unit.compiled_params["extra_seconds"] == 2
    assert unit.compiled_params["window_frames"] == 480
    assert unit.compiled_params["duration_frames"] == 481
    assert unit.compiled_params["tick_count"] == 4


def test_constellation_units_reject_foreign_owner_and_bad_values():
    with pytest.raises(ContentUnitValidationError):
        create_sucrose_constellation_c1(_c1_request(owner_key="character:other"))
    with pytest.raises(ContentUnitValidationError):
        create_sucrose_constellation_c1(_c1_request(slot=None))
    with pytest.raises(ContentUnitValidationError):
        create_sucrose_constellation_c1(_c1_request((0.0,)))
    with pytest.raises(ContentUnitValidationError):
        create_sucrose_constellation_c2(_c2_request((2.0,)) if False else _c2_request((0.0,)))


# --- C3 / C5：天赋等级提升 --------------------------------------------------


def test_c3_boosts_elemental_skill_talent_level():
    unit = create_sucrose_constellation_c3(_c3_request())

    assert unit.effects[0].unlock.threshold == 3
    assert unit.talent_level_boosts == {"elemental_skill": 3}
    assert unit.compiled_params["boost"] == 3
    assert unit.compiled_params["cap"] == 15


def test_c5_boosts_elemental_burst_talent_level():
    unit = create_sucrose_constellation_c5(_c5_request())

    assert unit.effects[0].unlock.threshold == 5
    assert unit.talent_level_boosts == {"elemental_burst": 3}


def test_talent_boost_rejects_cap_below_boost():
    with pytest.raises(ContentUnitValidationError):
        create_sucrose_constellation_c3(_c3_request((3.0, 2.0)))
    with pytest.raises(ContentUnitValidationError):
        create_sucrose_constellation_c5(_c5_request((0.0, 15.0)))


# --- C4：计次与随机减冷却 ---------------------------------------------------


def test_c4_unit_mounts_hook_with_asset_values():
    unit = create_sucrose_constellation_c4(_c4_request())

    assert unit.effects[0].unlock.threshold == 4
    assert len(unit.event_hooks) == 1
    hook = unit.event_hooks[0]
    assert isinstance(hook, SucroseC4HitCounterHook)
    assert unit.compiled_params == {
        "name": "合成命座行",
        "hit_count": 7,
        "min_reduction_seconds": 1,
        "max_reduction_seconds": 7,
        "count_interval_frames": 6,
    }
    # 源站以负数表示「减少」，上限取绝对值。
    assert unit.compiled_params["max_reduction_seconds"] == 7


def test_c4_emits_cooldown_batch_after_seven_hits():
    hook = SucroseC4HitCounterHook(owner_ref=OWNER_REF, slot=1)
    context = _context(seed=7)
    results = [
        hook.handle(
            _damage_event(frame=FRAME + offset * 6, tag=f"普通攻击{(offset % 4) + 1}"),
            context,
        )
        for offset in range(7)
    ]

    # 前六次只计数，不产出意图。
    for result in results[:6]:
        assert result.cooldown_requests == ()
    assert hook.hit_count == 0  # 第七次触发后清零。

    batches = results[-1].cooldown_requests
    assert len(batches) == 1
    batch = cast(CooldownMutationBatchRequest, batches[0])
    assert batch.frame == FRAME + 36
    assert len(batch.requests) == 1
    request = cast(ReduceRemainingCooldownRequest, batch.requests[0])
    assert request.key.ability_key == "elemental_skill"
    assert request.key.subject.subject_id == OWNER_REF
    assert 60 <= request.reduction_frames <= 420
    assert request.reduction_frames % 60 == 0


def test_c4_rate_limit_suppresses_hits_inside_interval():
    hook = SucroseC4HitCounterHook(owner_ref=OWNER_REF, slot=1)
    context = _context(seed=1)

    for _ in range(10):
        hook.handle(_damage_event(frame=FRAME), context)

    # 同一帧的重复命中只计一次（0.1 秒 = 6 帧的计次间隔）。
    assert hook.hit_count == 1
    hook.handle(_damage_event(frame=FRAME + 6), context)
    assert hook.hit_count == 2


def test_c4_ignores_other_tags_and_non_enemy_targets():
    hook = SucroseC4HitCounterHook(owner_ref=OWNER_REF, slot=1)
    context = _context(seed=1)

    # 元素战技 / 元素爆发 / 下落攻击都不在 C4 的触发面里。
    assert hook.handle(_damage_event(tag="元素战技"), context).cooldown_requests == ()
    assert hook.handle(_damage_event(tag="元素爆发"), context).cooldown_requests == ()
    assert hook.handle(_damage_event(tag="下落攻击"), context).cooldown_requests == ()
    # 己方目标不算「命中敌人」。
    assert hook.handle(_damage_event(target_id="character:slot_2"), context).cooldown_requests == ()
    # 他人造成的伤害不计入。
    assert hook.handle(_damage_event(source=SLOT_2), context).cooldown_requests == ()
    assert hook.hit_count == 0


def test_c4_random_roll_is_deterministic_and_uniform():
    """同种子同结果；七档整数秒都可达（1–7 秒）。"""

    def roll(seed: int) -> int:
        hook = SucroseC4HitCounterHook(owner_ref=OWNER_REF, slot=1)
        context = _context(seed=seed)
        result = None
        for offset in range(7):
            result = hook.handle(_damage_event(frame=FRAME + offset * 6), context)
        assert result is not None
        request = cast(
            ReduceRemainingCooldownRequest,
            cast(CooldownMutationBatchRequest, result.cooldown_requests[0]).requests[0],
        )
        return request.reduction_frames // 60

    assert roll(11) == roll(11)
    seen = {roll(seed) for seed in range(40)}
    assert seen <= {1, 2, 3, 4, 5, 6, 7}
    assert len(seen) >= 5  # 覆盖多档（合成随机源的分布检查不做精确等概率断言）


def test_c4_hook_rejects_bad_interval():
    with pytest.raises(ContentUnitValidationError):
        SucroseC4HitCounterHook(owner_ref=OWNER_REF, slot=1, hit_count=0)
    with pytest.raises(ContentUnitValidationError):
        SucroseC4HitCounterHook(owner_ref=OWNER_REF, slot=1, min_reduction_seconds=8)
    with pytest.raises(ContentUnitValidationError):
        SucroseC4HitCounterHook(owner_ref=OWNER_REF, slot=1, count_interval_frames=-1)


# --- C6：Buff 定义与染色触发 ------------------------------------------------


def test_c6_buff_definition_declares_eight_element_terms():
    definition = build_c6_damage_bonus_buff_definition()

    assert definition.definition_key == SUCROSE_C6_BUFF_DEFINITION_KEY
    assert definition.handler_key == _C6_KEY
    assert len(definition.attribute_modifiers) == len(MAGE_ENHANCEMENT_ELEMENTS)
    assert [item.term_key for item in definition.attribute_modifiers] == [
        c6_damage_bonus_term_key(element) for element in MAGE_ENHANCEMENT_ELEMENTS
    ]


def test_c6_modifier_values_fill_only_target_element():
    values = c6_damage_bonus_modifier_values(Element.PYRO, 0.2)

    assert len(values) == len(MAGE_ENHANCEMENT_ELEMENTS)
    filled = [value.value for value in values if value.value != 0.0]
    assert filled == [pytest.approx(0.2)]
    fire_index = MAGE_ENHANCEMENT_ELEMENTS.index(Element.PYRO)
    assert values[fire_index].term_key == c6_damage_bonus_term_key(Element.PYRO)


def test_c6_unit_mounts_hook_and_both_definitions():
    unit = create_sucrose_constellation_c6(_c6_request())

    assert unit.effects[0].unlock.threshold == 6
    assert len(unit.event_hooks) == 1
    assert isinstance(unit.event_hooks[0], SucroseC6AbsorbedBonusHook)
    keys = {definition.definition_key for definition in unit.buff_definitions}
    assert keys == {
        SUCROSE_C6_BUFF_DEFINITION_KEY,
        SUCROSE_C6_MAGE_ENHANCEMENT_BUFF_DEFINITION_KEY,
    }
    # 未点 C2：时长取爆发生命周期 361 帧。
    assert unit.compiled_params["duration_frames"] == SUCROSE_SPIRIT_DURATION_FRAMES
    assert unit.compiled_params["damage_bonus"] == pytest.approx(SUCROSE_C6_DAMAGE_BONUS)


def test_c6_duration_follows_c2_extension():
    unit = create_sucrose_constellation_c6(_c6_request(constellation=6))

    # 已点 C2（归属上下文命座 ≥2）→ 窗口 8s，C6 时长同步为 481 帧。
    assert unit.compiled_params["duration_frames"] == 481


def test_c6_hook_grants_whole_team_including_sucrose():
    hook = SucroseC6AbsorbedBonusHook(owner_ref=OWNER_REF, slot=1)
    context = _context()
    event = _damage_event(
        request_id=f"tick:spirit:1:{SUCROSE_SPIRIT_ABSORBED_TICK_IMPACT_KEY}:absorbed",
        element=Element.PYRO,
    )

    result = hook.handle(event, context)
    requests = tuple(result.buff_requests)

    assert len(requests) == 3  # 全队（含砂糖自己）
    assert {cast(Any, request).definition_key for request in requests} == {
        SUCROSE_C6_BUFF_DEFINITION_KEY
    }
    for request in requests:
        assert cast(Any, request).duration_frames == SUCROSE_SPIRIT_DURATION_FRAMES
        assert cast(Any, request).target_ref in {SLOT_1, SLOT_2, SLOT_3}


def test_c6_hook_adds_mage_enhancement_when_roster_active():
    hook = SucroseC6AbsorbedBonusHook(owner_ref=OWNER_REF, slot=1)
    context = _context(mage_slots=(1, 2))
    event = _damage_event(
        request_id=f"tick:{SUCROSE_SPIRIT_ABSORBED_TICK_IMPACT_KEY}:absorbed",
        element=Element.HYDRO,
    )

    requests = tuple(hook.handle(event, context).buff_requests)

    main = [r for r in requests if cast(Any, r).definition_key == SUCROSE_C6_BUFF_DEFINITION_KEY]
    mage = [
        r
        for r in requests
        if cast(Any, r).definition_key == SUCROSE_C6_MAGE_ENHANCEMENT_BUFF_DEFINITION_KEY
    ]
    assert len(main) == 3
    # 魔导名录含槽位 1、2：只给他们追加 +8.57142%。
    assert [cast(Any, r).target_ref for r in mage] == [SLOT_1, SLOT_2]
    values = [value.value for value in cast(Any, mage[0]).modifier_values if value.value]
    assert values == [pytest.approx(SUCROSE_C6_MAGE_ENHANCEMENT_BONUS)]
    assert pytest.approx(0.0857142) == SUCROSE_C6_MAGE_ENHANCEMENT_BONUS


def test_c6_hook_ignores_non_absorbed_and_foreign_damage():
    hook = SucroseC6AbsorbedBonusHook(owner_ref=OWNER_REF, slot=1)
    context = _context()

    # 风伤段（非染色）不触发。
    assert (
        tuple(hook.handle(_damage_event(request_id="tick:spirit:1:anemo"), context).buff_requests)
        == ()
    )
    # 他人造成的染色伤害不触发。
    assert (
        tuple(
            hook.handle(
                _damage_event(
                    request_id=f"x:{SUCROSE_SPIRIT_ABSORBED_TICK_IMPACT_KEY}",
                    source=SLOT_2,
                ),
                context,
            ).buff_requests
        )
        == ()
    )


def test_c6_mage_enhancement_values_share_element_order():
    """魔导增强与本体各自一套词条键，互不串台。"""

    mage = mage_enhancement_modifier_values(Element.CRYO, 0.0857142)
    main = c6_damage_bonus_modifier_values(Element.CRYO, 0.2)

    assert [value.term_key for value in mage] == [
        mage_enhancement_term_key(element) for element in MAGE_ENHANCEMENT_ELEMENTS
    ]
    assert [value.term_key for value in main] == [
        c6_damage_bonus_term_key(element) for element in MAGE_ENHANCEMENT_ELEMENTS
    ]
    assert {value.term_key for value in mage}.isdisjoint({value.term_key for value in main})


def test_c6_rejects_non_positive_bonus():
    with pytest.raises(ContentUnitValidationError):
        create_sucrose_constellation_c6(_c6_request((0.0,)))
    with pytest.raises(ContentUnitValidationError):
        create_sucrose_constellation_c6(_c6_request((1.5,)))


# --- 角色单元的 C1 / C2 静态切片 -------------------------------------------


def _character_unit(constellation: int, effect_params: dict[str, dict[str, object]]):
    return create_sucrose_content_unit(
        CharacterContentUnitRequest(
            handler_key=SUCROSE_CHARACTER_HANDLER_KEY,
            character_key=SUCROSE_ASSET_KEY,
            slot=1,
            talent_levels={"normal_attack": 1, "elemental_skill": 1, "elemental_burst": 1},
            talent_scalings=sucrose_helpers.minimal_sucrose_scaling_entries(),
            constellation=constellation,
            effect_params=effect_params,
        )
    )


def test_character_unit_c1_raises_charges_and_switches_recovery_mode():

    params = {
        "c1": _effect_params((1.0,)),
        "c2": _effect_params((2.0,)),
    }

    base = _character_unit(0, params)
    base_skill = next(
        definition
        for definition in base.cooldown_definitions
        if definition.key.ability_key == "elemental_skill"
    )
    assert base_skill.max_charges == 1
    assert base_skill.recovery_mode is CooldownRecoveryMode.SERIAL

    c1_unit = _character_unit(1, params)
    skill = next(
        definition
        for definition in c1_unit.cooldown_definitions
        if definition.key.ability_key == "elemental_skill"
    )
    assert skill.max_charges == 2
    assert skill.recovery_mode is CooldownRecoveryMode.INDEPENDENT
    # 爆发冷却不受 C1 影响。
    burst = next(
        definition
        for definition in c1_unit.cooldown_definitions
        if definition.key.ability_key == "elemental_burst"
    )
    assert burst.max_charges == 1


def test_character_unit_c2_extends_spirit_window_and_ticks():
    params = {"c1": _effect_params((1.0,)), "c2": _effect_params((2.0,))}

    base = _character_unit(0, params)
    base_spirit = cast(Any, base.created_object_types["sucrose.large_wind_spirit"])
    assert base_spirit.duration_frames == 361
    assert base_spirit.tick_count == SUCROSE_SPIRIT_TICK_COUNT

    c2_unit = _character_unit(2, params)
    spirit = cast(Any, c2_unit.created_object_types["sucrose.large_wind_spirit"])
    assert spirit.duration_frames == 481
    assert spirit.tick_count == 4


def test_character_unit_requires_asset_row_when_constellation_unlocked():
    with pytest.raises(ContentUnitValidationError):
        _character_unit(1, {})
    with pytest.raises(ContentUnitValidationError):
        _character_unit(2, {"c1": _effect_params((1.0,))})
