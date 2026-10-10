"""砂糖「魔女的前夜礼·七循之理」的单元测试：名录判定、触发判据、投放范围与工厂接线。

数值全部为合成数据（见测试规范 §3.2）：真实资产效果行的正确性由资产构建与
校验链路承担，这里只锁定
「魔导名录 -> 激活门槛 -> 触发事实 -> 投放范围 -> ApplyBuffRequest」、
「标记 Buff 存在性 -> 伤害 provider 词条」与
「资产效果行 -> 效果工厂 -> hook + Buff 定义 + provider」三条接线。

前夜礼是**队伍级**机制：本期只有砂糖一名魔导角色，单元测试用 ``MageRoster``
直接搭出「一名 / 两名魔导角色」的名录，不依赖资产库里另有魔导角色。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ASSET_KEY,
    SUCROSE_C6_MAGE_ENHANCEMENT_BONUS,
    SUCROSE_C6_MAGE_ENHANCEMENT_BUFF_DEFINITION_KEY,
    SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
    SUCROSE_WITCHES_EVE_DAMAGE_TAGS,
    SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY,
    SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES,
    SUCROSE_WITCHES_EVE_LARGE_MECHANIC_KEY,
    SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY,
    SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES,
    SUCROSE_WITCHES_EVE_SMALL_MECHANIC_KEY,
)
from genshin_sim.content.characters.mondstadt.sucrose.effects import (
    create_sucrose_passive_witches_eve,
    read_witches_eve_asset_values,
)
from genshin_sim.content.characters.mondstadt.sucrose.hooks import (
    SucroseWitchesEveLargeSpiritHook,
    SucroseWitchesEveSmallSpiritHook,
)
from genshin_sim.content.characters.mondstadt.sucrose.modifiers import (
    MAGE_ENHANCEMENT_ELEMENTS,
    SucroseWitchesEveDamageBonusProvider,
    build_c6_mage_enhancement_buff_definition,
    build_witches_eve_large_buff_definition,
    build_witches_eve_small_buff_definition,
    mage_enhancement_modifier_values,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.definitions.effects import EffectKind, UnlockKind
from genshin_sim.content.hooks import HookContext
from genshin_sim.content.registries import EffectContentUnitRequest
from genshin_sim.content.team.mage import (
    MAGE_ACTIVATION_THRESHOLD,
    MAGE_MARKER_KEY,
    MageRoster,
    build_mage_roster,
)
from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.entity_states import CharacterRuntimeState
from genshin_sim.core.events import EventType, GameEvent, SpaceEntityCreatedPayload
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.damage import DamageModifierStage
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope
from tests.helpers.events import make_action_started_event

OWNER_REF = "character:slot_1"
SLOT_1 = AttributeSubjectRef.character("character:slot_1")
SLOT_2 = AttributeSubjectRef.character("character:slot_2")
SLOT_3 = AttributeSubjectRef.character("character:slot_3")
FRAME = 100

_SMALL_KEY = SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY
_LARGE_KEY = SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY


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
) -> HookContext:
    """构造 hook 求值上下文：队伍运行态 + 可选魔导名录。"""

    simulation = SimulationContext()
    if mage_slots is not None:
        simulation.register_system(MageRoster(mage_slots))
    return HookContext(frame=FRAME, round=0, simulation=simulation, states=_team(team_slots))


def _requests(result: object) -> tuple[ApplyBuffRequest, ...]:
    return cast(tuple[ApplyBuffRequest, ...], tuple(getattr(result, "buff_requests", ())))


def _skill_start(
    *,
    frame: int = FRAME,
    slot: int = 1,
    ability: str | None = "elemental_skill",
) -> GameEvent:
    return make_action_started_event(frame, slot, ability)


def _spirit_created_event(
    *,
    frame: int = FRAME,
    owner_key: str = OWNER_REF,
    tags: tuple[str, ...] = ("sucrose.large_wind_spirit",),
) -> GameEvent:
    return GameEvent(
        EventType.SPACE_ENTITY_CREATED,
        frame,
        SpaceEntityCreatedPayload(
            frame,
            SpatialEntity(
                entity_id="created_object:sucrose.large_wind_spirit:1",
                kind=SpatialEntityKind.CREATED_OBJECT,
                position=Vector3(),
                owner_key=owner_key,
                tags=tags,
            ),
        ),
    )


# --- 魔导名录 ---------------------------------------------------------------


def test_mage_roster_activation_requires_two_mages():
    assert MageRoster((1,)).is_active is False
    assert MageRoster((1, 2)).is_active is True
    assert MAGE_ACTIVATION_THRESHOLD == 2


def test_mage_roster_normalizes_and_exposes_slots():
    roster = MageRoster((3, 1, 2, 2))

    assert roster.slots == (1, 2, 3)
    assert roster.contains_slot(2) is True
    assert roster.contains_slot(4) is False


def test_mage_roster_rejects_non_positive_slots():
    with pytest.raises(ContentUnitValidationError):
        MageRoster((0, 1))


def test_build_mage_roster_collects_marked_character_units():
    from genshin_sim.content.definitions.content_unit import (
        ContentUnit,
        ContentUnitOwnerType,
    )

    marked = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:a",
        handler_key="character.a",
        version="test",
        slot=2,
        metadata={MAGE_MARKER_KEY: True},
    )
    unmarked = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:b",
        handler_key="character.b",
        version="test",
        slot=3,
        metadata={"purpose": "not_a_mage"},
    )
    wrong_owner = ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key="artifact:c",
        handler_key="artifact.c",
        version="test",
        slot=4,
        metadata={MAGE_MARKER_KEY: True},
    )

    assert build_mage_roster((marked, unmarked, wrong_owner)).slots == (2,)


# --- 小型风灵档：触发与投放 -------------------------------------------------


def test_small_spirit_hook_applies_to_whole_team_when_active():
    hook = SucroseWitchesEveSmallSpiritHook(owner_ref=OWNER_REF, slot=1)
    context = _context(mage_slots=(1, 2))

    requests = _requests(hook.handle(_skill_start(), context))

    assert [request.target_ref.entity_id for request in requests] == [
        "character:slot_1",
        "character:slot_2",
        "character:slot_3",
    ]
    request = requests[0]
    assert request.definition_key == SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY
    assert request.duration_frames == SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES
    assert request.frame == FRAME
    assert request.modifier_values == ()


def test_small_spirit_hook_ignores_other_abilities_and_slots():
    hook = SucroseWitchesEveSmallSpiritHook(owner_ref=OWNER_REF, slot=1)
    context = _context(mage_slots=(1, 2))

    assert _requests(hook.handle(_skill_start(ability="elemental_burst"), context)) == ()
    assert _requests(hook.handle(_skill_start(slot=2), context)) == ()
    assert _requests(hook.handle(_skill_start(ability=None), context)) == ()


def test_small_spirit_hook_stays_inactive_with_single_mage():
    hook = SucroseWitchesEveSmallSpiritHook(owner_ref=OWNER_REF, slot=1)

    event = _skill_start()
    # 名录只有砂糖自己（生产环境默认形态）：不投放。
    assert _requests(hook.handle(event, _context(mage_slots=(1,)))) == ()
    # 名录未注册（装配期未收集）：同样按未生效处理。
    assert _requests(hook.handle(event, _context())) == ()


def test_small_spirit_hook_validates_construction():
    with pytest.raises(ContentUnitValidationError):
        SucroseWitchesEveSmallSpiritHook(owner_ref="", slot=1)
    with pytest.raises(ContentUnitValidationError):
        SucroseWitchesEveSmallSpiritHook(owner_ref=OWNER_REF, slot=0)
    with pytest.raises(ContentUnitValidationError):
        SucroseWitchesEveSmallSpiritHook(owner_ref=OWNER_REF, slot=1, duration_frames=0)


# --- 大型风灵档：触发与投放 -------------------------------------------------


def test_large_spirit_hook_applies_to_mage_characters_only():
    hook = SucroseWitchesEveLargeSpiritHook(owner_ref=OWNER_REF, slot=1)
    context = _context(mage_slots=(1, 3))

    requests = _requests(hook.handle(_spirit_created_event(), context))

    assert [request.target_ref.entity_id for request in requests] == [
        "character:slot_1",
        "character:slot_3",
    ]
    request = requests[0]
    assert request.definition_key == SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY
    assert request.duration_frames == SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES
    assert request.frame == FRAME


def test_large_spirit_hook_ignores_foreign_created_objects():
    hook = SucroseWitchesEveLargeSpiritHook(owner_ref=OWNER_REF, slot=1)
    context = _context(mage_slots=(1, 2))

    # 归属不是砂糖、以及标签不含大型风灵键的创建物都不触发。
    foreign = _spirit_created_event(owner_key="character:slot_2")
    assert _requests(hook.handle(foreign, context)) == ()
    other_tag = _spirit_created_event(tags=("other.object",))
    assert _requests(hook.handle(other_tag, context)) == ()
    assert _requests(hook.handle(_skill_start(), context)) == ()


def test_large_spirit_hook_stays_inactive_with_single_mage():
    hook = SucroseWitchesEveLargeSpiritHook(owner_ref=OWNER_REF, slot=1)

    assert _requests(hook.handle(_spirit_created_event(), _context(mage_slots=(1,)))) == ()
    assert _requests(hook.handle(_spirit_created_event(), _context())) == ()


def test_large_spirit_hook_validates_construction():
    with pytest.raises(ContentUnitValidationError):
        SucroseWitchesEveLargeSpiritHook(owner_ref="  ", slot=1)
    with pytest.raises(ContentUnitValidationError):
        SucroseWitchesEveLargeSpiritHook(owner_ref=OWNER_REF, slot=-1)
    with pytest.raises(ContentUnitValidationError):
        SucroseWitchesEveLargeSpiritHook(owner_ref=OWNER_REF, slot=1, duration_frames=-5)


# --- Buff 定义 --------------------------------------------------------------


def test_witches_eve_buff_definitions_are_team_wide_markers():
    small = build_witches_eve_small_buff_definition()
    large = build_witches_eve_large_buff_definition()

    for definition in (small, large):
        assert definition.marker_only is True
        assert definition.target_kinds == frozenset({AttributeSubjectKind.CHARACTER})
        assert definition.application_policy is BuffApplicationPolicy.REFRESH
        assert definition.value_refresh_policy is BuffValueRefreshPolicy.REPLACE_LATEST
        assert definition.max_stacks == 1
        assert definition.attribute_modifiers == ()
        assert definition.handler_key == SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY

    # 两档独立冲突键：互不覆盖、各自计时。
    assert small.conflict_key != large.conflict_key
    assert small.definition_key == SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY
    assert large.definition_key == SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY
    assert small.mechanic_key == SUCROSE_WITCHES_EVE_SMALL_MECHANIC_KEY
    assert large.mechanic_key == SUCROSE_WITCHES_EVE_LARGE_MECHANIC_KEY


# --- 伤害 provider ----------------------------------------------------------


class _PresencePort:
    """目标状态只读端口替身：按给定集合回答 Buff 存在性。"""

    def __init__(self, present: frozenset[tuple[str, str]]) -> None:
        self._present = present
        self.queries: list[tuple[str, str, int]] = []

    def has_buff(
        self,
        *,
        target_ref: AttributeSubjectRef,
        definition_key: str,
        frame: int,
    ) -> bool:
        self.queries.append((target_ref.entity_id, definition_key, frame))
        return (target_ref.entity_id, definition_key) in self._present

    def active_stack_count(
        self,
        *,
        target_ref: AttributeSubjectRef,
        definition_key: str,
        frame: int,
    ) -> int:
        return (
            1
            if self.has_buff(target_ref=target_ref, definition_key=definition_key, frame=frame)
            else 0
        )


def _query(
    *,
    source: AttributeSubjectRef = SLOT_1,
    tag: str = "元素战技",
    frame: int = FRAME,
    formula_key: str = FORMULA_KEY_GENERAL,
) -> DamageQuery:
    """provider 查询替身：只带上 provider 实际读取的四个字段。

    与 ``tests.helpers.damage.provider_query_stub`` 同款形态，避免为了单测
    构造整条伤害请求（provider 契约只读这些字段）。
    """

    return cast(
        "DamageQuery",
        SimpleNamespace(
            request=SimpleNamespace(
                frame=frame,
                formula_key=formula_key,
                main_attack_tag=tag,
                source_ref=source,
            )
        ),
    )


# 前夜礼的 provider 只读「标记 Buff 是否存在」，不读结算作用域（内部直接丢弃
# scope），单测因此传一个显式转换过的空作用域，不为它搭整套属性解析器。
_NO_SCOPE = cast(DamageResolutionScope, None)


def _provider(**overrides: Any) -> SucroseWitchesEveDamageBonusProvider:
    kwargs: dict[str, Any] = {
        "owner_ref": OWNER_REF,
        "scope_key": "small",
        "buff_definition_key": SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY,
        "bonus": 0.05,
        "display_name": "测试·小型风灵增伤",
    }
    kwargs.update(overrides)
    return SucroseWitchesEveDamageBonusProvider(**kwargs)


def test_provider_contributes_only_when_marker_buff_present():
    provider = _provider()
    present = frozenset({("character:slot_1", _SMALL_KEY)})
    port = _PresencePort(present)
    provider.bind_runtime_ports(target_status_port=port)

    terms = provider.contribute(_query(), scope=_NO_SCOPE)

    assert len(terms) == 1
    term = terms[0]
    assert term.stage is DamageModifierStage.DAMAGE_BONUS_ADD
    assert term.value == pytest.approx(0.05)
    assert term.provider_key == provider.provider_spec.provider_key
    assert port.queries == [("character:slot_1", _SMALL_KEY, FRAME)]

    # 未持有标记 Buff 的角色（含未投放的队友）不贡献。
    assert provider.contribute(_query(source=SLOT_2), scope=_NO_SCOPE) == ()


def test_provider_without_port_contributes_nothing():
    provider = _provider()

    assert provider.contribute(_query(), scope=_NO_SCOPE) == ()


def test_provider_filters_tags_and_formula():
    provider = _provider()
    port = _PresencePort(
        frozenset(
            {
                ("character:slot_1", SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY),
                ("character:slot_2", SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY),
            }
        )
    )
    provider.bind_runtime_ports(target_status_port=port)

    # 五类标签全部命中。
    for tag in sorted(SUCROSE_WITCHES_EVE_DAMAGE_TAGS):
        assert len(provider.contribute(_query(tag=tag), scope=_NO_SCOPE)) == 1
    # 反应标签与非通用公式都不命中（DAMAGE_BONUS_ADD 只在通用公式放行）。
    assert provider.contribute(_query(tag="超导"), scope=_NO_SCOPE) == ()
    transformative = "damage_formula.transformative"
    assert provider.contribute(_query(formula_key=transformative), scope=_NO_SCOPE) == ()
    # 非角色来源（创建物自己的主体）不命中。
    foreign = AttributeSubjectRef.target("target:1")
    assert provider.contribute(_query(source=foreign), scope=_NO_SCOPE) == ()


def test_provider_rejects_non_positive_bonus():
    with pytest.raises(ContentUnitValidationError):
        _provider(bonus=0.0)
    with pytest.raises(ContentUnitValidationError):
        _provider(bonus=-0.1)


# --- C6 魔导增强（常量与 Buff 定义） ----------------------------------------


def test_c6_mage_enhancement_constant_matches_source_value():
    # 源站砂糖 C6 descriptionBuff 的魔导增强数值，不做分数化简（§11.7 裁决 7）。
    assert pytest.approx(0.0857142) == SUCROSE_C6_MAGE_ENHANCEMENT_BONUS


def test_c6_mage_enhancement_definition_declares_every_element():
    definition = build_c6_mage_enhancement_buff_definition()

    assert definition.definition_key == SUCROSE_C6_MAGE_ENHANCEMENT_BUFF_DEFINITION_KEY
    assert definition.marker_only is False
    assert len(definition.attribute_modifiers) == len(MAGE_ENHANCEMENT_ELEMENTS)
    stages = {template.stage for template in definition.attribute_modifiers}
    assert stages == {ModifierStage.FLAT_ADD}
    assert definition.application_policy is BuffApplicationPolicy.REFRESH
    assert definition.value_refresh_policy is BuffValueRefreshPolicy.REPLACE_LATEST
    assert definition.max_stacks == 1


def test_c6_mage_enhancement_values_fill_one_element_only():
    definition = build_c6_mage_enhancement_buff_definition()
    values = mage_enhancement_modifier_values(Element.PYRO, SUCROSE_C6_MAGE_ENHANCEMENT_BONUS)

    assert len(values) == len(definition.attribute_modifiers)
    filled = [value.value for value in values if value.value != 0.0]
    assert filled == [pytest.approx(SUCROSE_C6_MAGE_ENHANCEMENT_BONUS)]
    # 与模板逐条匹配（框架要求 modifier_values 完整覆盖 term_key）。
    assert {value.term_key for value in values} == {
        template.term_key for template in definition.attribute_modifiers
    }


# --- 效果工厂 ---------------------------------------------------------------


def _effect_params(values: tuple[float, ...]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "魔女的前夜礼·七循之理",
        "components": [
            {"kind": "numeric", "format": "number", "values": [value]} for value in values
        ],
    }


def _request(params: dict[str, object], *, slot: int | None = 1) -> EffectContentUnitRequest:
    return EffectContentUnitRequest(
        handler_key=SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
        effect_key=f"{SUCROSE_ASSET_KEY}:passive:9",
        effect_kind="passive",
        owner_type="character",
        owner_key=SUCROSE_ASSET_KEY,
        slot=slot,
        params=params,
        unlock_key="passive:9",
    )


_ASSET_COMPONENTS = (2.0, 15.0, 0.0571428, 20.0, 0.0714285)


def test_read_witches_eve_asset_values_maps_durations_and_ratios():
    small_frames, small_bonus, large_frames, large_bonus = read_witches_eve_asset_values(
        _effect_params(_ASSET_COMPONENTS)
    )

    assert small_frames == 900
    assert small_bonus == pytest.approx(0.0571428)
    assert large_frames == 1200
    assert large_bonus == pytest.approx(0.0714285)


def test_read_witches_eve_asset_values_ignores_mage_threshold_component():
    """门槛人数（``number_1``）不在此建模：资产写多少都不读入、不校验。

    「魔导·秘仪」是否激活是 ``MageRoster`` 的事（按共享常量判定），效果包不替它
    建模——故门槛分量被按位置消费后丢弃（这里用 3 证明它不再触发任何报错）。
    """

    small_frames, small_bonus, large_frames, large_bonus = read_witches_eve_asset_values(
        _effect_params((3.0, 15.0, 0.0571428, 20.0, 0.0714285))
    )

    assert small_frames == 900
    assert small_bonus == pytest.approx(0.0571428)
    assert large_frames == 1200
    assert large_bonus == pytest.approx(0.0714285)


def test_read_witches_eve_asset_values_rejects_bad_components():
    # 小型 / 大型档比例越界。
    with pytest.raises(ContentUnitValidationError):
        read_witches_eve_asset_values(_effect_params((2.0, 15.0, 0.0, 20.0, 0.07)))
    with pytest.raises(ContentUnitValidationError):
        read_witches_eve_asset_values(_effect_params((2.0, 15.0, 0.05, 20.0, 1.1)))
    # 秒数非正。
    with pytest.raises(ContentUnitValidationError):
        read_witches_eve_asset_values(_effect_params((2.0, 0.0, 0.05, 20.0, 0.07)))
    # components 缺失。
    with pytest.raises(ContentUnitValidationError):
        read_witches_eve_asset_values({"schema_version": 1, "name": "x"})


def test_factory_mounts_hooks_definitions_and_providers():
    unit = create_sucrose_passive_witches_eve(_request(_effect_params(_ASSET_COMPONENTS)))

    assert unit.handler_key == SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY
    assert unit.slot == 1
    assert len(unit.effects) == 1
    effect = unit.effects[0]
    assert effect.kind is EffectKind.PASSIVE
    assert effect.unlock.kind is UnlockKind.ALWAYS

    assert {hook.hook_key for hook in unit.event_hooks} == {
        f"sucrose.passive.witches_eve.small:{OWNER_REF}",
        f"sucrose.passive.witches_eve.large:{OWNER_REF}",
    }
    assert {definition.definition_key for definition in unit.buff_definitions} == {
        SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY,
        SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY,
    }
    providers = tuple(unit.damage_modifier_providers)
    assert len(providers) == 2
    assert {provider.provider_spec.writes for provider in providers} == {
        frozenset({DamageModifierStage.DAMAGE_BONUS_ADD})
    }
    # provider_key 必须互不相同，否则 DamageModifierIndex 会判重复。
    assert len({provider.provider_spec.provider_key for provider in providers}) == 2
    assert unit.compiled_params["small_duration_frames"] == 900
    assert unit.compiled_params["large_duration_frames"] == 1200
    # 门槛人数不在效果包里建模（激活由 MageRoster 判定），故不进 compiled_params。
    assert "min_mage_count" not in unit.compiled_params


def test_factory_rejects_foreign_owner_and_missing_slot():
    with pytest.raises(ContentUnitValidationError):
        create_sucrose_passive_witches_eve(
            EffectContentUnitRequest(
                handler_key=SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
                effect_key="character:other:passive:9",
                effect_kind="passive",
                owner_type="character",
                owner_key="character:other",
                slot=1,
                params=_effect_params(_ASSET_COMPONENTS),
            )
        )
    with pytest.raises(ContentUnitValidationError):
        create_sucrose_passive_witches_eve(_request(_effect_params(_ASSET_COMPONENTS), slot=None))
