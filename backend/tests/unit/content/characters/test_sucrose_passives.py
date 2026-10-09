"""砂糖固有天赋 A1 / A4 的单元测试：触发判据、投放范围、数值来源与工厂接线。

数值全部为合成数据（见测试规范 §3.2）：真实资产效果行的正确性由资产构建与
校验链路承担，这里只锁定
「反应/伤害事实 -> 触发判据 -> 目标筛选 -> ApplyBuffRequest」与
「资产效果行 -> 效果工厂 -> hook + Buff 定义」两条接线。

A1 的「与被扩散元素同元素」需要在运行期读出**槽位元素**；运行期唯一可读来源是
能量系统的角色档案，因此本文件的上下文替身按 ``CharacterEnergyProfile`` 搭一份
最小能量运行期（与 ``tests/unit/core/systems/energy`` 同构），A4 的快照读数则
复用 ``tests/helpers/damage.make_attribute_resolver`` 的合成属性环境。
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_A1_BUFF_DEFINITION_KEY,
    SUCROSE_A1_MASTERY_TERM_KEY,
    SUCROSE_A1_MECHANIC_KEY,
    SUCROSE_A1_TRIGGER_REACTION_KEYS,
    SUCROSE_A4_BUFF_DEFINITION_KEY,
    SUCROSE_A4_MASTERY_RATIO,
    SUCROSE_A4_MASTERY_TERM_KEY,
    SUCROSE_A4_MECHANIC_KEY,
    SUCROSE_ASSET_KEY,
    SUCROSE_PASSIVE_A1_HANDLER_KEY,
    SUCROSE_PASSIVE_A4_HANDLER_KEY,
)
from genshin_sim.content.characters.mondstadt.sucrose.effects import (
    create_sucrose_passive_a1,
    create_sucrose_passive_a4,
    read_a1_asset_values,
    read_a4_asset_values,
)
from genshin_sim.content.characters.mondstadt.sucrose.hooks import (
    SucroseCatalystConversionHook,
    SucroseMollisFavoniusHook,
)
from genshin_sim.content.characters.mondstadt.sucrose.modifiers import (
    build_a1_mastery_buff_definition,
    build_a4_mastery_buff_definition,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.definitions.effects import EffectKind, UnlockKind
from genshin_sim.content.hooks import HookContext
from genshin_sim.content.registries import EffectContentUnitRequest
from genshin_sim.core.attributes import (
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeResolveOptions,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.attributes.resolver import AttributeResolver
from genshin_sim.core.elements import AuraKind
from genshin_sim.core.entity_states import CharacterRuntimeState
from genshin_sim.core.events import EventEngine
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffModifierValue,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.energy import (
    CharacterEnergyProfile,
    CharacterEnergyStore,
    EnergyElement,
    EnergyRuntime,
    EnergyTransitQueue,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import SWIRL_REACTION_KEY
from tests.helpers.damage import make_attribute_resolver
from tests.helpers.events import (
    make_damage_resolved_event,
    make_reaction_occurrence_event,
)

OWNER_REF = "character:slot_1"
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.sucrose.passive")
# 合成精通：A4 折算比例 0.2 -> 单次加成 40。
SUCROSE_FIXTURE_MASTERY = 200.0
SUCROSE_FIXTURE_DURATION_FRAMES = 480


class _UnusedResolution:
    """能量运行期构造所需的最小解析结果形状（与 golden 单测同构）。"""

    final_value: float


class _UnusedResolver:
    """能量运行期构造需要的端口替身：本文件不调用能量 API。"""

    def resolve(
        self,
        query: AttributeQuery,
        *,
        options: AttributeResolveOptions | None = None,
    ) -> _UnusedResolution:
        raise NotImplementedError


def _team(elements: tuple[str | None, ...]) -> tuple[TeamRuntimeState, EnergyRuntime]:
    """按槽位元素搭最小队伍 + 能量运行期。

    ``None`` 表示该角色**没有能量档案**：角色运行态存在、能量存储里查不到，
    用于覆盖「槽位元素不可得时自然跳过」的防御分支。
    """

    characters = tuple(
        CharacterRuntimeState(
            slot=index,
            character_key=f"character:{element or 'no_profile'}_{index}",
            level=90,
        )
        for index, element in enumerate(elements, start=1)
    )
    team = TeamRuntimeState(characters)
    entries = []
    for character, element in zip(characters, elements, strict=True):
        if element is None:
            continue
        ref = AttributeSubjectRef.character(character.combat_entity_id)
        entries.append(
            (
                CharacterEnergyProfile(
                    ref,
                    character.character_key,
                    EnergyElement(element),
                    80.0,
                ),
                character.energy,
            )
        )
    runtime = EnergyRuntime(
        _UnusedResolver(),
        team,
        CharacterEnergyStore(entries),
        EnergyTransitQueue(),
        EventEngine(),
    )
    return team, runtime


def _context(
    elements: tuple[str | None, ...],
    *,
    sucrose_mastery: float | None = None,
) -> HookContext:
    """构造 hook 求值上下文：队伍运行态 + 能量运行期（+ 可选属性解析器）。"""

    team, energy_runtime = _team(elements)
    simulation = SimulationContext()
    simulation.register_system(energy_runtime)
    if sucrose_mastery is not None:
        simulation.register_system(
            make_attribute_resolver(
                (AttributeSubjectRef.character(OWNER_REF),),
                target=AttributeSubjectRef.target("target:1"),
                source_context=SOURCE_CONTEXT,
                elemental_mastery=sucrose_mastery,
            )
        )
    return HookContext(frame=0, round=0, simulation=simulation, states=team)


def _a1_hook(**overrides: Any) -> SucroseCatalystConversionHook:
    kwargs: dict[str, Any] = {
        "owner_ref": OWNER_REF,
        "slot": 1,
        "duration_frames": SUCROSE_FIXTURE_DURATION_FRAMES,
        "mastery_flat": 50.0,
    }
    kwargs.update(overrides)
    return SucroseCatalystConversionHook(**kwargs)


def _a4_hook(**overrides: Any) -> SucroseMollisFavoniusHook:
    kwargs: dict[str, Any] = {
        "owner_ref": OWNER_REF,
        "slot": 1,
        "ratio": SUCROSE_A4_MASTERY_RATIO,
        "duration_frames": SUCROSE_FIXTURE_DURATION_FRAMES,
    }
    kwargs.update(overrides)
    return SucroseMollisFavoniusHook(**kwargs)


def _buff_requests(result) -> tuple[ApplyBuffRequest, ...]:
    return cast(tuple[ApplyBuffRequest, ...], tuple(result.buff_requests))


def _skill_hit(*, source: str = OWNER_REF, target: str = "target:1", tag: str = "元素战技"):
    return make_damage_resolved_event(
        44,
        "damage:44",
        source_key=source,
        target_key=target,
        main_attack_tag=tag,
    )


# --- A1 触媒置换术：触发判据 -------------------------------------------------


def test_a1_hook_applies_mastery_to_same_element_teammates_only():
    hook = _a1_hook()
    context = _context(("anemo", "pyro", "hydro"))
    event = make_reaction_occurrence_event(
        120, SWIRL_REACTION_KEY, "occ:swirl", aura_kind=AuraKind.PYRO
    )

    requests = _buff_requests(hook.handle(event, context))

    # 只有与火元素一致的队友（槽位 2）入选；水队友与砂糖自己被排除。
    assert [request.target_ref.entity_id for request in requests] == ["character:slot_2"]
    request = requests[0]
    assert request.definition_key == SUCROSE_A1_BUFF_DEFINITION_KEY
    assert request.duration_frames == SUCROSE_FIXTURE_DURATION_FRAMES
    assert request.frame == 120
    assert request.source_context == RuntimeSourceRef(
        RuntimeSourceKind.MECHANIC,
        SUCROSE_A1_MECHANIC_KEY,
    )
    assert request.modifier_values == (BuffModifierValue(SUCROSE_A1_MASTERY_TERM_KEY, 50.0),)


def test_a1_hook_accepts_both_swirl_and_stellar_swirl():
    assert (
        frozenset({SWIRL_REACTION_KEY, STELLAR_SWIRL_REACTION_KEY})
        == SUCROSE_A1_TRIGGER_REACTION_KEYS
    )
    hook = _a1_hook()
    context = _context(("anemo", "pyro"))
    for reaction_key in sorted(SUCROSE_A1_TRIGGER_REACTION_KEYS):
        event = make_reaction_occurrence_event(
            120, reaction_key, f"occ:{reaction_key}", aura_kind=AuraKind.PYRO
        )
        requests = _buff_requests(hook.handle(event, context))
        assert [request.target_ref.entity_id for request in requests] == ["character:slot_2"]


def test_a1_hook_maps_frozen_aura_to_cryo():
    hook = _a1_hook()
    context = _context(("anemo", "cryo", "pyro"))
    event = make_reaction_occurrence_event(
        120, SWIRL_REACTION_KEY, "occ:frozen", aura_kind=AuraKind.FROZEN
    )

    requests = _buff_requests(hook.handle(event, context))

    # FROZEN 与染色判定第 4 档同口径映射为冰元素。
    assert [request.target_ref.entity_id for request in requests] == ["character:slot_2"]


def test_a1_hook_ignores_reactions_from_other_sources():
    hook = _a1_hook()
    context = _context(("anemo", "pyro"))
    others = make_reaction_occurrence_event(
        120,
        SWIRL_REACTION_KEY,
        "occ:other",
        source_key="character:slot_2",
        aura_kind=AuraKind.PYRO,
    )
    assert _buff_requests(hook.handle(others, context)) == ()


def test_a1_hook_ignores_non_swirl_reactions():
    hook = _a1_hook()
    context = _context(("anemo", "pyro"))
    event = make_reaction_occurrence_event(
        120, "reaction.bloom", "occ:bloom", aura_kind=AuraKind.PYRO
    )
    assert _buff_requests(hook.handle(event, context)) == ()


def test_a1_hook_ignores_auras_without_element_mapping():
    hook = _a1_hook()
    context = _context(("anemo", "dendro"))
    for aura_kind in (AuraKind.DENDRO, AuraKind.QUICKEN):
        event = make_reaction_occurrence_event(
            120, SWIRL_REACTION_KEY, f"occ:{aura_kind.value}", aura_kind=aura_kind
        )
        assert _buff_requests(hook.handle(event, context)) == ()
    # 未携带 transition（反应事实缺字段）时按未生效处理，不抛异常。
    missing = make_reaction_occurrence_event(120, SWIRL_REACTION_KEY, "occ:missing")
    assert _buff_requests(hook.handle(missing, context)) == ()


def test_a1_hook_skips_teammates_without_energy_profile():
    hook = _a1_hook()
    # 槽位 2 没有能量档案（查不到槽位元素）：跳过该槽位，不引入特例分支。
    context = _context(("anemo", None))
    event = make_reaction_occurrence_event(
        120, SWIRL_REACTION_KEY, "occ:pyro", aura_kind=AuraKind.PYRO
    )
    assert _buff_requests(hook.handle(event, context)) == ()


def test_a1_hook_requires_positive_configuration():
    with pytest.raises(ContentUnitValidationError):
        _a1_hook(duration_frames=0)
    with pytest.raises(ContentUnitValidationError):
        _a1_hook(mastery_flat=0.0)
    with pytest.raises(ContentUnitValidationError):
        _a1_hook(owner_ref="")


# --- A4 小小的慧风：触发判据与快照 -------------------------------------------


def test_a4_hook_snapshots_mastery_for_every_teammate():
    hook = _a4_hook()
    context = _context(("anemo", "pyro", "hydro"), sucrose_mastery=SUCROSE_FIXTURE_MASTERY)

    requests = _buff_requests(hook.handle(_skill_hit(), context))

    # 快照 200 精通 × 20% = 40；目标为除砂糖外的全体角色（不筛元素）。
    assert [request.target_ref.entity_id for request in requests] == [
        "character:slot_2",
        "character:slot_3",
    ]
    assert [request.order for request in requests] == [0, 1]
    for request in requests:
        assert request.definition_key == SUCROSE_A4_BUFF_DEFINITION_KEY
        assert request.duration_frames == SUCROSE_FIXTURE_DURATION_FRAMES
        assert len(request.modifier_values) == 1
        assert request.modifier_values[0].term_key == SUCROSE_A4_MASTERY_TERM_KEY
        assert request.modifier_values[0].value == pytest.approx(40.0)
    assert requests[0].source_context == RuntimeSourceRef(
        RuntimeSourceKind.MECHANIC,
        SUCROSE_A4_MECHANIC_KEY,
    )


def test_a4_hook_accepts_skill_and_burst_tags_without_discriminating_hits():
    hook = _a4_hook()
    context = _context(("anemo", "pyro"), sucrose_mastery=SUCROSE_FIXTURE_MASTERY)
    for tag in ("元素战技", "元素爆发"):
        assert _buff_requests(hook.handle(_skill_hit(tag=tag), context))


def test_a4_hook_ignores_other_sources_non_trigger_tags_and_character_targets():
    hook = _a4_hook()
    context = _context(("anemo", "pyro"), sucrose_mastery=SUCROSE_FIXTURE_MASTERY)
    assert _buff_requests(hook.handle(_skill_hit(source="character:slot_2"), context)) == ()
    assert _buff_requests(hook.handle(_skill_hit(tag="普通攻击1"), context)) == ()
    assert _buff_requests(hook.handle(_skill_hit(tag="重击"), context)) == ()
    assert _buff_requests(hook.handle(_skill_hit(target="character:slot_2"), context)) == ()
    assert _buff_requests(hook.handle(_skill_hit(target="created_object:spirit"), context)) == ()


def test_a4_hook_is_inert_without_attribute_resolver_or_mastery():
    hook = _a4_hook()
    # 属性解析器未接线：视为不生效，不投放。
    unwired = _context(("anemo", "pyro"))
    assert _buff_requests(hook.handle(_skill_hit(), unwired)) == ()
    # 快照为 0：折算结果 0，同样不投放零值 Buff。
    zero = _context(("anemo", "pyro"), sucrose_mastery=0.0)
    assert _buff_requests(hook.handle(_skill_hit(), zero)) == ()


def test_a4_hook_reads_mastery_through_the_registered_resolver():
    """快照取解析器读数：换成 120 精通后加成随之变为 24。"""

    hook = _a4_hook()
    context = _context(("anemo", "pyro"), sucrose_mastery=120.0)
    requests = _buff_requests(hook.handle(_skill_hit(), context))
    assert requests[0].modifier_values[0].value == pytest.approx(24.0)

    resolver = context.simulation.get_system(AttributeResolver)
    assert isinstance(resolver, AttributeResolver)
    resolution = resolver.resolve(
        AttributeQuery(
            subject_ref=AttributeSubjectRef.character(OWNER_REF),
            attribute_key=STAT_ELEMENTAL_MASTERY,
            frame=0,
        )
    )
    assert resolution.final_value == pytest.approx(120.0)


# --- 效果工厂：资产效果行读数与切片 ------------------------------------------


def _effect_request(
    handler_key: str,
    *,
    name: str,
    values: tuple[float, ...],
    owner_key: str = SUCROSE_ASSET_KEY,
    slot: int | None = 1,
) -> EffectContentUnitRequest:
    return EffectContentUnitRequest(
        handler_key=handler_key,
        effect_key=f"{owner_key}:passive:4",
        effect_kind="passive",
        owner_type="character",
        owner_key=owner_key,
        slot=slot,
        params={
            "schema_version": 1,
            "name": name,
            # EffectSpec.params 必须是 JSON 兼容值：分量序列用 list。
            "components": [
                {"kind": "numeric", "format": "number", "values": [value]} for value in values
            ],
        },
        unlock_key="passive:4",
    )


def test_read_a1_asset_values_reads_mastery_and_seconds():
    params = _effect_request(
        SUCROSE_PASSIVE_A1_HANDLER_KEY, name="触媒置换术", values=(50.0, 8.0)
    ).params
    assert read_a1_asset_values(params) == (50.0, 480)


@pytest.mark.parametrize(
    ("values", "expected"),
    (
        pytest.param((0.2, 8.0), (0.2, 480), id="ratio-and-seconds"),
        pytest.param((1.0, 2.0), (1.0, 120), id="upper-bound-ratio"),
    ),
)
def test_read_a4_asset_values_reads_ratio_and_seconds(values, expected):
    params = _effect_request(
        SUCROSE_PASSIVE_A4_HANDLER_KEY, name="小小的慧风", values=values
    ).params
    assert read_a4_asset_values(params) == expected


@pytest.mark.parametrize(
    "values",
    (
        pytest.param((8.0, 0.2), id="seconds-in-ratio-slot"),
        pytest.param((0.0, 8.0), id="zero-ratio"),
        pytest.param((1.2, 8.0), id="ratio-above-one"),
    ),
)
def test_read_a4_asset_values_rejects_component_misalignment(values):
    """组件错位（序号/秒数混入比例位）必须报错，而不是静默折算出近零加成。"""

    params = _effect_request(
        SUCROSE_PASSIVE_A4_HANDLER_KEY, name="小小的慧风", values=values
    ).params
    with pytest.raises(ContentUnitValidationError, match="比例"):
        read_a4_asset_values(params)


def test_read_a1_asset_values_rejects_missing_components():
    with pytest.raises(ContentUnitValidationError, match="components"):
        read_a1_asset_values({"schema_version": 1, "name": "触媒置换术"})


def test_passive_a1_factory_builds_hook_and_buff_slices():
    unit = create_sucrose_passive_a1(
        _effect_request(SUCROSE_PASSIVE_A1_HANDLER_KEY, name="触媒置换术", values=(50.0, 8.0))
    )

    assert unit.handler_key == SUCROSE_PASSIVE_A1_HANDLER_KEY
    assert unit.owner_key == SUCROSE_ASSET_KEY
    assert unit.slot == 1
    effect = unit.effects[0]
    assert effect.kind is EffectKind.PASSIVE
    assert effect.unlock.kind is UnlockKind.ASCENSION
    assert effect.unlock.threshold == 1
    assert len(unit.event_hooks) == 1
    hook = cast(SucroseCatalystConversionHook, unit.event_hooks[0])
    assert hook.hook_key == f"sucrose.passive.a1:{OWNER_REF}"
    assert hook.subscriptions == ("REACTION_OCCURRED",)
    assert hook.owner_ref == OWNER_REF
    assert [definition.definition_key for definition in unit.buff_definitions] == [
        SUCROSE_A1_BUFF_DEFINITION_KEY
    ]
    assert unit.compiled_params["mastery_flat"] == 50.0
    assert unit.compiled_params["duration_frames"] == 480


def test_passive_a4_factory_builds_hook_and_buff_slices():
    unit = create_sucrose_passive_a4(
        _effect_request(
            SUCROSE_PASSIVE_A4_HANDLER_KEY,
            name="小小的慧风",
            values=(0.2, 8.0),
        )
    )

    assert unit.handler_key == SUCROSE_PASSIVE_A4_HANDLER_KEY
    effect = unit.effects[0]
    assert effect.unlock.kind is UnlockKind.ASCENSION
    assert effect.unlock.threshold == 4
    assert len(unit.event_hooks) == 1
    hook = cast(SucroseMollisFavoniusHook, unit.event_hooks[0])
    assert hook.hook_key == f"sucrose.passive.a4:{OWNER_REF}"
    assert hook.subscriptions == ("DAMAGE_RESOLVED",)
    assert [definition.definition_key for definition in unit.buff_definitions] == [
        SUCROSE_A4_BUFF_DEFINITION_KEY
    ]
    assert unit.compiled_params["mastery_ratio"] == 0.2
    assert unit.compiled_params["duration_frames"] == 480


@pytest.mark.parametrize(
    "factory",
    (create_sucrose_passive_a1, create_sucrose_passive_a4),
    ids=("a1", "a4"),
)
def test_passive_factories_reject_other_owners_and_missing_slot(factory):
    other = _effect_request(
        SUCROSE_PASSIVE_A1_HANDLER_KEY,
        name="触媒置换术",
        values=(50.0, 8.0),
        owner_key="character:10000002",
    )
    with pytest.raises(ContentUnitValidationError, match="砂糖资产"):
        factory(other)


def test_passive_factories_reject_missing_slot():
    request = _effect_request(
        SUCROSE_PASSIVE_A1_HANDLER_KEY,
        name="触媒置换术",
        values=(50.0, 8.0),
        slot=None,
    )
    with pytest.raises(ContentUnitValidationError, match="槽位"):
        create_sucrose_passive_a1(request)


def test_passive_factories_reject_missing_effect_name():
    request = _effect_request(SUCROSE_PASSIVE_A1_HANDLER_KEY, name="触媒置换术", values=(50.0, 8.0))
    params = dict(request.params)
    params.pop("name")
    broken = EffectContentUnitRequest(
        handler_key=request.handler_key,
        effect_key=request.effect_key,
        effect_kind=request.effect_kind,
        owner_type=request.owner_type,
        owner_key=request.owner_key,
        slot=request.slot,
        params=params,
    )
    with pytest.raises(ContentUnitValidationError, match="名称"):
        create_sucrose_passive_a1(broken)


# --- Buff 定义：二次转化分桶标记与覆盖刷新 ------------------------------------


def test_a1_buff_definition_keeps_product_reconvertible():
    definition = build_a1_mastery_buff_definition()
    template = definition.attribute_modifiers[0]

    assert definition.definition_key == SUCROSE_A1_BUFF_DEFINITION_KEY
    assert definition.mechanic_key == SUCROSE_A1_MECHANIC_KEY
    assert definition.handler_key == SUCROSE_PASSIVE_A1_HANDLER_KEY
    assert definition.target_kinds == frozenset({AttributeSubjectKind.CHARACTER})
    assert definition.max_stacks == 1
    assert template.term_key == SUCROSE_A1_MASTERY_TERM_KEY
    assert template.target_key == STAT_ELEMENTAL_MASTERY
    assert template.stage == ModifierStage.FLAT_ADD
    # A1 是固定值来源，不是「读其他属性再折算」的转化效果，产物默认可被二次转化。
    assert template.reconvertible is True


def test_a4_buff_definition_marks_product_non_reconvertible():
    definition = build_a4_mastery_buff_definition()
    template = definition.attribute_modifiers[0]

    assert definition.definition_key == SUCROSE_A4_BUFF_DEFINITION_KEY
    assert definition.mechanic_key == SUCROSE_A4_MECHANIC_KEY
    assert definition.handler_key == SUCROSE_PASSIVE_A4_HANDLER_KEY
    assert definition.target_kinds == frozenset({AttributeSubjectKind.CHARACTER})
    assert definition.max_stacks == 1
    assert template.term_key == SUCROSE_A4_MASTERY_TERM_KEY
    assert template.stage == ModifierStage.FLAT_ADD
    # A4 的数值由「读砂糖精通再折算」得出，属转化效果：产物不可再被二次转化。
    assert template.reconvertible is False


@pytest.mark.parametrize(
    "builder",
    (build_a1_mastery_buff_definition, build_a4_mastery_buff_definition),
    ids=("a1", "a4"),
)
def test_passive_buff_definitions_refresh_in_place(builder):
    definition = builder()
    assert definition.application_policy is BuffApplicationPolicy.REFRESH
    assert definition.value_refresh_policy is BuffValueRefreshPolicy.REPLACE_LATEST
    assert definition.display_name
    # 每个定义各自独立冲突键，两个天赋互不覆盖。
    assert definition.conflict_key.startswith(definition.handler_key)


def test_passive_buff_definitions_use_distinct_conflict_keys():
    a1 = build_a1_mastery_buff_definition()
    a4 = build_a4_mastery_buff_definition()
    assert a1.conflict_key != a4.conflict_key
    assert a1.definition_key != a4.definition_key


def test_hook_context_stub_is_accepted_by_module_contract():
    """上下文替身必须满足模块公开契约（防止后续重构悄悄改变入参形状）。"""

    context = _context(("anemo", "pyro"), sucrose_mastery=100.0)
    assert isinstance(context, HookContext)
    assert context.states is not None
    assert cast(Any, context.simulation.get_system(EnergyRuntime)) is not None
    assert _team(("anemo",))[0].characters[0].slot == 1
