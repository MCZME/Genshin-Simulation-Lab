# 单一关注点：星扩散在元素交互协调器中的全链路闭环。
# 覆盖：风触发替代普通扩散、风伤害结算、风旋等级按目标累加、同帧风伤害
# 去重、6 级爆炸冰伤害与 1U 冰附着、附着触发星超导的后续反应链路、
# 辉映·星扩散 Buff 的申请与 REFRESH 顺延、爆炸范围内前台角色的关系过滤与
# 位置级跳跃能力 Buff。
from __future__ import annotations

import pytest

from genshin_sim.application.assembly.damage_profiles import (
    create_default_damage_profile_registry,
)
from genshin_sim.core.attributes import (
    AttributeResolver,
    AttributeSubjectKind,
    AttributeSubjectRef,
    BaseAttributeSet,
    ModifierProviderIndex,
    create_public_attribute_registry,
)
from genshin_sim.core.coordination.elemental_reaction import (
    ElementalInteractionCoordinator,
    ElementalStateFrameCoordinator,
    ReactionSpatialPlanningAdapter,
    ReactionTargetRelation,
    StellarSwirlVortexExpiryCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.capabilities import (
    ReactionCapabilityEvidence,
    ReactionEligibilityView,
)
from genshin_sim.core.coordination.elemental_reaction.observers import (
    CharacterTransformativeSourceObserver,
)
from genshin_sim.core.coordination.elemental_reaction.settlement_coordinator import (
    ElementalSettlementCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.status import (
    superconduct_buff_definition,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
    stellar_radiance_buff_definition,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_swirl_buffs import (
    STELLAR_SWIRL_JUMP_BOOST_BUFF_DEFINITION_KEY,
    STELLAR_SWIRL_JUMP_BOOST_DURATION_FRAMES,
    STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY,
    STELLAR_SWIRL_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY,
    STELLAR_SWIRL_RADIANCE_DURATION_FRAMES,
    stellar_swirl_jump_boost_buff_definition,
    stellar_swirl_radiance_buff_definition,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.events import (
    DamageResolvedPayload,
    ElementalInteractionResolvedPayload,
    EventType,
    ReactionOccurredPayload,
)
from genshin_sim.core.impacts import ElementalApplicationSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import (
    ACTIVE_CHARACTER_ENTITY_ID,
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.aura import (
    AuraApplicationProfileRegistry,
    AuraRuntime,
    AuraStrength,
)
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.buff import (
    BuffDefinitionRegistry,
    BuffResolver,
    BuffRuntime,
    BuffStore,
)
from genshin_sim.core.systems.damage import (
    DamageRequestHandler,
    DamageResolver,
    FixedCriticalDecisionProvider,
    create_default_damage_formula_registry,
)
from genshin_sim.core.systems.damage.level_multipliers import transformative_level_multiplier
from genshin_sim.core.systems.reaction import (
    PolestarFieldState,
    StellarSwirlVortexState,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct import (
    STELLAR_CONDUCT_CAPABILITY_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl import (
    STELLAR_SWIRL_CAPABILITY_KEY,
    stellar_swirl_ice_aura_application_profile,
)
from genshin_sim.core.systems.reaction.states import STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES

TARGET_1_ENTITY_ID = "target:star"
TARGET_2_ENTITY_ID = "target:moon"
CHARACTER_ENTITY_ID = "character:slot_1"


class _DualCapabilityPort:
    """同时提供星超导与星扩散 capability 的固定队伍准入证据。"""

    def evidence_for(self, frame: int, team_ref: str) -> ReactionEligibilityView:
        provider = ElementalSubjectRef.character(CHARACTER_ENTITY_ID)
        return ReactionEligibilityView(
            team_ref,
            frame,
            (
                ReactionCapabilityEvidence(STELLAR_CONDUCT_CAPABILITY_KEY, provider),
                ReactionCapabilityEvidence(STELLAR_SWIRL_CAPABILITY_KEY, provider),
            ),
        )


class _PreparedSwirlCoordinator:
    def __init__(
        self,
        *,
        targets: tuple[tuple[str, str, Vector3], ...] = (
            ("star", TARGET_1_ENTITY_ID, Vector3(0.0, 0.0, 0.0)),
            ("moon", TARGET_2_ENTITY_ID, Vector3(5.0, 0.0, 0.0)),
        ),
        active_character_position: Vector3 | None = None,
    ) -> None:
        entities = [
            SpatialEntity(spatial_entity_id, SpatialEntityKind.TARGET, position)
            for _, spatial_entity_id, position in targets
        ]
        if active_character_position is not None:
            entities.append(
                SpatialEntity(
                    ACTIVE_CHARACTER_ENTITY_ID,
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=active_character_position,
                    active_slot=1,
                )
            )
        space = Space(tuple(entities))
        self.space_runtime = SpaceRuntime(
            space=space,
            team_state=TeamRuntimeState(
                (
                    CharacterRuntimeState(
                        1,
                        "character:test",
                        90,
                        combat_entity_id=CHARACTER_ENTITY_ID,
                    ),
                )
            ),
            targets=TargetRuntimeCollection(
                tuple(
                    TargetRuntimeState(target_id, level=90, spatial_entity_id=spatial_entity_id)
                    for target_id, spatial_entity_id, _ in targets
                )
            ),
        )
        self.context = SimulationContext(space_runtime=self.space_runtime)
        attribute_registry = create_public_attribute_registry()
        attribute_resolver = AttributeResolver(
            definitions=attribute_registry,
            base_attributes=BaseAttributeSet(()),
            modifier_index=ModifierProviderIndex((), registry=attribute_registry),
        )
        self.aura_runtime = AuraRuntime()
        self.icd_runtime = AuraIcdRuntime()
        self.reaction_runtime = create_default_reaction_bootstrap().create_runtime()
        self.spatial_planning_port = ReactionSpatialPlanningAdapter(space)
        self.buff_runtime = BuffRuntime(
            definition_registry=BuffDefinitionRegistry(
                (
                    superconduct_buff_definition(),
                    stellar_radiance_buff_definition(),
                    stellar_swirl_radiance_buff_definition(),
                    stellar_swirl_jump_boost_buff_definition(),
                )
            ),
            resolver=BuffResolver(),
            buff_store=BuffStore(),
            event_engine=self.context.events,
        )
        self.frame_coordinator = ElementalStateFrameCoordinator(
            self.aura_runtime,
            self.icd_runtime,
            self.reaction_runtime,
            stellar_swirl_vortex_expiry_coordinator=StellarSwirlVortexExpiryCoordinator(
                reaction_state_port=self.reaction_runtime,
                spatial_planning_port=self.spatial_planning_port,
            ),
        )
        self.damage_handler = DamageRequestHandler(
            DamageResolver(
                attribute_resolver=attribute_resolver,
                formula_registry=create_default_damage_formula_registry(
                    critical_decision_provider=FixedCriticalDecisionProvider()
                ),
            ),
            profile_registry=create_default_damage_profile_registry(),
        )
        interaction_coordinator = ElementalInteractionCoordinator(
            aura_runtime=self.aura_runtime,
            icd_runtime=self.icd_runtime,
            reaction_runtime=self.reaction_runtime,
            damage_handler=self.damage_handler,
            frame_coordinator=self.frame_coordinator,
            transformative_source_observer=CharacterTransformativeSourceObserver(
                attribute_resolver
            ),
            reaction_eligibility_port=_DualCapabilityPort(),
            spatial_planning_port=self.spatial_planning_port,
            stellar_buff_port=self.buff_runtime,
        )
        self.settlement = ElementalSettlementCoordinator(
            interaction_coordinator,
            reaction_runtime=self.reaction_runtime,
            aura_runtime=self.aura_runtime,
            frame_coordinator=self.frame_coordinator,
            damage_handler=self.damage_handler,
            buff_runtime=self.buff_runtime,
            aura_application_profile_registry=AuraApplicationProfileRegistry(
                (stellar_swirl_ice_aura_application_profile(),)
            ),
        )
        self._application_sequence = 0

    def apply_element(
        self,
        element: Element,
        *,
        frame: int,
        target_refs: tuple[str, ...] = ("star",),
    ) -> ImpactRequest:
        self._application_sequence += 1
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.APPLY_AURA,
            impact_key=f"test.stellar.{element.value}",
            owner_slot=1,
            request_id=f"root:stellar:{element.value}:{self._application_sequence}",
            target_refs=target_refs,
            elemental_application_spec=ElementalApplicationSpec(
                impact_ref=f"impact:{element.value}:{self._application_sequence}",
                element=element,
                elemental_strength=AuraStrength.WEAK,
                elemental_amount=AuraAmount.one(),
            ),
        )

    def stellar_resolutions(self):
        resolutions = []
        for event in self.context.events.frame_events:
            if event.event_type is not EventType.DAMAGE_RESOLVED:
                continue
            assert isinstance(event.payload, DamageResolvedPayload)
            resolution = event.payload.result.stellar_reaction_resolution
            if resolution is not None:
                resolutions.append(resolution)
        return tuple(resolutions)

    def occurred_reaction_keys(self) -> tuple[str, ...]:
        return tuple(
            event.payload.occurrence.reaction_key
            for event in self.context.events.frame_events
            if event.event_type is EventType.REACTION_OCCURRED
            and isinstance(event.payload, ReactionOccurredPayload)
        )

    def cryo_aura_amount(self, target_entity_id: str) -> AuraAmount | None:
        component = self.aura_runtime.view(
            ElementalSubjectRef.target(target_entity_id)
        ).component_for(AuraKind.CRYO)
        return None if component is None else component.current_amount

    def vortex(self) -> StellarSwirlVortexState | None:
        return next(
            (
                state
                for state in self.reaction_runtime.state_records
                if isinstance(state, StellarSwirlVortexState)
            ),
            None,
        )

    def swirl_radiance_buffs(self, frame: int):
        return self.buff_runtime.reader.active(
            frame,
            definition_key=STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY,
        )

    def jump_boost_buffs(self, frame: int):
        return self.buff_runtime.reader.active(
            frame,
            definition_key=STELLAR_SWIRL_JUMP_BOOST_BUFF_DEFINITION_KEY,
        )


def _level_90_multiplier() -> float:
    return transformative_level_multiplier(
        TransformativeReactionSourceKind.CHARACTER,
        90,
    )[1]


def test_swirl_interaction_creates_vortex_and_settles_wind_damage() -> None:
    prepared = _PreparedSwirlCoordinator()
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ANEMO, frame=0),
    )

    assert "reaction.stellar_swirl" in prepared.occurred_reaction_keys()
    vortex = prepared.vortex()
    assert vortex is not None
    assert vortex.level == 1
    assert vortex.expires_at_frame == STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES
    assert vortex.last_reaction_source_ref.source_key == CHARACTER_ENTITY_ID
    assert prepared.space_runtime.get_entity(vortex.space_entity_ref) is not None

    # 风伤害：单体、复合模式、基础值来自 90 级等级系数。
    # 唯一参与者按名次取 0.60 权重（固定权重、不按参与人数重归一化）。
    resolutions = prepared.stellar_resolutions()
    assert len(resolutions) == 1
    wind = resolutions[0]
    assert wind.input.stellar_base_multiplier == pytest.approx(0.75)
    assert wind.input.mode == "reaction_composite"
    assert len(wind.components) == 1
    # 最终数值闭环已隐含 0.60 权重；权重字段本身由公式层持有。
    assert wind.official_damage == pytest.approx(_level_90_multiplier() * 0.75 * 0.60)


def test_swirl_interaction_accumulates_level_per_target_without_cross_target_dedup() -> None:
    prepared = _PreparedSwirlCoordinator()
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0, target_refs=("star", "moon")),
    )
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ANEMO, frame=0, target_refs=("star", "moon")),
    )

    vortex = prepared.vortex()
    assert vortex is not None
    # 风旋等级按目标数累加：两个带冰目标各贡献 1 级。
    assert vortex.level == 2
    # 每个目标各承受一次风伤害（去重按目标判定，不跨目标）。
    assert len(prepared.stellar_resolutions()) == 2


def test_swirl_interaction_explodes_at_level_six_with_ice_damage_and_cryo_attachment() -> None:
    prepared = _PreparedSwirlCoordinator()
    for _ in range(6):
        prepared.settlement.settle_aura_impact(
            prepared.context,
            prepared.apply_element(Element.CRYO, frame=0),
        )
        prepared.settlement.settle_aura_impact(
            prepared.context,
            prepared.apply_element(Element.ANEMO, frame=0),
        )

    # 6 级立即爆炸：风旋终结，全场唯一风旋消失。
    assert prepared.vortex() is None
    resolutions = prepared.stellar_resolutions()
    # 风伤害去重：同一目标 30 帧窗口内 6 次风事件只承受一次风伤害。
    wind_resolutions = [
        item for item in resolutions if item.input.stellar_base_multiplier == pytest.approx(0.75)
    ]
    assert len(wind_resolutions) == 1
    # 冰爆炸：等级 3~6 系数为 3，半径 8 覆盖两个目标。
    ice_resolutions = [
        item for item in resolutions if item.input.stellar_base_multiplier == pytest.approx(3.0)
    ]
    assert len(ice_resolutions) == 2
    for item in ice_resolutions:
        assert len(item.components) == 1
        assert item.components[0].participant_ref.entity_id == CHARACTER_ENTITY_ID

    # 冰爆炸对命中目标附着 1U 冰元素，归因伤害源。
    # 1U 附着经标准 20% 初始损耗后存留 4/5。
    assert prepared.cryo_aura_amount(TARGET_1_ENTITY_ID) == AuraAmount("4/5")
    assert prepared.cryo_aura_amount(TARGET_2_ENTITY_ID) == AuraAmount("4/5")

    # 冰附着的 1U 冰元素可触发星超导：风 → 冰附着 → 星超导的闭环成立。
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=0),
    )
    assert "reaction.stellar_conduct" in prepared.occurred_reaction_keys()
    assert any(
        isinstance(state, PolestarFieldState) for state in prepared.reaction_runtime.state_records
    )


def test_swirl_interaction_expires_vortex_and_settles_explosion_at_lifetime_frame() -> None:
    prepared = _PreparedSwirlCoordinator()
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ANEMO, frame=0),
    )
    assert prepared.vortex() is not None
    assert len(prepared.stellar_resolutions()) == 1  # 只有风伤害

    # 推进到 180 帧到期：帧规范化物化风旋到期并结算冰爆炸。
    prepared.settlement.update_frame(prepared.context, STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES)

    assert prepared.vortex() is None
    resolutions = prepared.stellar_resolutions()
    # 等级 1 爆炸半径 6：T1（锚点）与 T2（距离 5）都在范围内，各一段冰伤害。
    assert len(resolutions) == 3
    explosion = resolutions[-1]
    assert explosion.input.stellar_base_multiplier == pytest.approx(2.0)
    assert len(explosion.components) == 1
    assert explosion.official_damage == pytest.approx(_level_90_multiplier() * 2.0 * 0.60)
    # 1U 附着经标准 20% 初始损耗后存留 4/5。
    assert prepared.cryo_aura_amount(TARGET_1_ENTITY_ID) == AuraAmount("4/5")
    assert prepared.cryo_aura_amount(TARGET_2_ENTITY_ID) == AuraAmount("4/5")


def test_swirl_interaction_applies_radiance_buff_to_capability_qualified_characters() -> None:
    prepared = _PreparedSwirlCoordinator()
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ANEMO, frame=0),
    )

    # 风触发后，capability 资格角色获得辉映·星扩散 Buff：
    # 词条固定 1.0、存续 480 帧基线、目标只含资格证据提供者。
    records = prepared.swirl_radiance_buffs(0)
    assert len(records) == 1
    record = records[0]
    assert record.state.target_ref.entity_id == CHARACTER_ENTITY_ID
    assert record.expires_at_frame == STELLAR_SWIRL_RADIANCE_DURATION_FRAMES
    resolved = record.state.resolved_modifiers
    assert len(resolved) == 1
    assert resolved[0].term_key == STELLAR_SWIRL_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY
    assert resolved[0].value == pytest.approx(1.0)

    # 未触发风扩散时不申请：新协调器在冰附着后无 Buff。
    fresh = _PreparedSwirlCoordinator()
    fresh.settlement.settle_aura_impact(
        fresh.context,
        fresh.apply_element(Element.CRYO, frame=0),
    )
    assert fresh.swirl_radiance_buffs(0) == ()


def test_swirl_interaction_refreshes_radiance_buff_on_repeated_wind_trigger() -> None:
    prepared = _PreparedSwirlCoordinator()
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ANEMO, frame=0),
    )

    # 帧内多次风触发只保留最后一次申请；过期前再次触发按 REFRESH 顺延。
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=100),
    )
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ANEMO, frame=100),
    )

    records = prepared.swirl_radiance_buffs(100)
    assert len(records) == 1
    record = records[0]
    assert record.last_applied_frame == 100
    assert record.expires_at_frame == 100 + STELLAR_SWIRL_RADIANCE_DURATION_FRAMES


def test_swirl_explosion_blocks_active_character_in_radius() -> None:
    """爆炸范围内的前台角色不是敌对关系：不受冰伤害、不被 1U 冰附着。

    爆炸 selection 显式声明 ``hostile_effect`` 资格策略，不继承
    ``AreaAroundPositionSelection`` 的 ``bloom_damage`` 默认值，因此"不自伤"
    由意图表达保证，而非依赖伤害 Effect 类型的白名单联合。
    """

    prepared = _PreparedSwirlCoordinator(active_character_position=Vector3(1.0, 0.0, 0.0))
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ANEMO, frame=0),
    )
    prepared.settlement.update_frame(prepared.context, STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES)

    # 等级 1 爆炸半径 6：T1（锚点，距离 0）、前台角色（距离 1）与
    # T2（距离 5）都在范围内，但只有两个敌人各承受一段冰伤害。
    character_outcomes = tuple(
        outcome
        for event in prepared.context.events.frame_events
        if event.event_type is EventType.ELEMENTAL_INTERACTION_RESOLVED
        and isinstance(event.payload, ElementalInteractionResolvedPayload)
        for outcome in event.payload.record.target_effect_outcomes
        if outcome.subject_ref.entity_id == ACTIVE_CHARACTER_ENTITY_ID
    )
    # 角色确实进入了爆炸范围目标集合，只是被关系过滤挡下（断言非空转）。
    assert character_outcomes
    assert all(item.relation is ReactionTargetRelation.SELF for item in character_outcomes)
    assert all(item.damage_outcome == "blocked_relation" for item in character_outcomes)

    resolutions = prepared.stellar_resolutions()
    assert len(resolutions) == 3
    assert prepared.cryo_aura_amount(TARGET_1_ENTITY_ID) == AuraAmount("4/5")
    assert prepared.cryo_aura_amount(TARGET_2_ENTITY_ID) == AuraAmount("4/5")
    character_aura = prepared.aura_runtime.view(
        ElementalSubjectRef.character(ACTIVE_CHARACTER_ENTITY_ID)
    )
    assert character_aura.component_for(AuraKind.CRYO) is None


def _explode_at_lifetime(prepared: _PreparedSwirlCoordinator) -> None:
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )
    prepared.settlement.settle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ANEMO, frame=0),
    )
    prepared.settlement.update_frame(prepared.context, STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES)


@pytest.mark.parametrize(
    ("explode_mode", "position", "expect_grant"),
    (
        ("expire", Vector3(1.0, 0.0, 0.0), True),
        ("expire", Vector3(20.0, 0.0, 0.0), False),
        ("level_six", Vector3(1.0, 0.0, 0.0), True),
    ),
    ids=("hit_at_lifetime", "outside_radius", "hit_at_level_six"),
)
def test_swirl_explosion_grants_jump_boost_by_range_and_path(
    explode_mode: str, position: Vector3, expect_grant: bool
) -> None:
    """爆炸范围内角色获得位置级跳跃 Buff；半径外不授予；6 级与到期爆炸同构。"""

    prepared = _PreparedSwirlCoordinator(active_character_position=position)
    if explode_mode == "level_six":
        for _ in range(6):
            prepared.settlement.settle_aura_impact(
                prepared.context,
                prepared.apply_element(Element.CRYO, frame=0),
            )
            prepared.settlement.settle_aura_impact(
                prepared.context,
                prepared.apply_element(Element.ANEMO, frame=0),
            )
        assert prepared.vortex() is None
        frame = 0
    else:
        _explode_at_lifetime(prepared)
        frame = STELLAR_SWIRL_VORTEX_LIFETIME_FRAMES

    records = prepared.jump_boost_buffs(frame)
    if not expect_grant:
        assert records == ()
        return
    assert len(records) == 1
    record = records[0]
    # 位置级主体：谁在前台谁享受，切人后由新前台自然接管。
    assert record.state.target_ref == AttributeSubjectRef.active_character("player_team")
    assert record.state.target_ref.kind is AttributeSubjectKind.ACTIVE_CHARACTER
    assert record.expires_at_frame == frame + STELLAR_SWIRL_JUMP_BOOST_DURATION_FRAMES
    # marker_only：Movement 尚无跳跃能力模型，不声明任何属性词条。
    assert record.state.resolved_modifiers == ()
