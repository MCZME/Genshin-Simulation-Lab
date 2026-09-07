# 单一关注点：Buff 最大生命同步协调器。
from __future__ import annotations

from dataclasses import dataclass

import pytest

from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STAT_HP_BASE,
    STAT_HP_MAX,
    AttributeResolver,
    AttributeSubjectKind,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.coordination.buff_max_hp_change import (
    BuffMaxHpChangeCommitError,
    BuffMaxHpChangeCoordinator,
    BuffMaxHpChangeReentrancyError,
    ProjectedBuffMaxHpResolver,
)
from genshin_sim.core.entity_states import HealthState
from genshin_sim.core.events import CharacterMaxHpChangedPayload, EventEngine, EventType
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffAttributeModifierProvider,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffDefinitionRegistry,
    BuffModifierValue,
    BuffPlanConflictError,
    BuffRemovalReason,
    BuffResolver,
    BuffRuntime,
    BuffStore,
    BuffStoreReader,
    BuffValueRefreshPolicy,
    RemoveBuffRequest,
)
from genshin_sim.core.systems.health import (
    CharacterDamageApplication,
    CharacterHealthStore,
    HealthRuntime,
    InvalidCurrentHealthError,
)

CHARACTER = AttributeSubjectRef.character("character:slot_1")
CHARACTER_2 = AttributeSubjectRef.character("character:slot_2")
TARGET = AttributeSubjectRef.target("target:target_1")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.MECHANIC, "mechanic.test_max_hp", "slot:1")


def _max_hp_definition(
    *,
    definition_key: str = "buff.test.max_hp",
    policy: BuffApplicationPolicy = BuffApplicationPolicy.REPLACE,
    value_refresh_policy: BuffValueRefreshPolicy = BuffValueRefreshPolicy.REPLACE_LATEST,
    target_kinds: frozenset[AttributeSubjectKind] = frozenset({AttributeSubjectKind.CHARACTER}),
) -> BuffDefinition:
    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key="mechanic.test_max_hp",
        handler_key="test.buff",
        conflict_key=definition_key,
        target_kinds=target_kinds,
        application_policy=policy,
        value_refresh_policy=value_refresh_policy,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key="max_hp_flat",
                target_key=STAT_HP_MAX,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({"test_max_hp"}),
    )


def _atk_definition() -> BuffDefinition:
    return BuffDefinition(
        definition_key="buff.test.atk",
        mechanic_key="mechanic.test_max_hp",
        handler_key="test.buff",
        conflict_key="buff.test.atk",
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REPLACE,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key="atk_percent",
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
            ),
        ),
        tags=frozenset({"test_atk"}),
    )


@dataclass
class _World:
    coordinator: BuffMaxHpChangeCoordinator
    buff_runtime: BuffRuntime
    health_runtime: HealthRuntime
    events: EventEngine
    buff_store: BuffStore
    resolver: AttributeResolver


def _world(*definitions: BuffDefinition) -> _World:
    registry = create_public_attribute_registry()
    buff_store = BuffStore()
    providers = tuple(
        BuffAttributeModifierProvider(definition, BuffStoreReader(buff_store))
        for definition in definitions
        if definition.attribute_modifiers
    )
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    CHARACTER,
                    BaseAttributeContribution(STAT_HP_BASE, 1000.0, SOURCE_CONTEXT),
                ),
                (
                    CHARACTER_2,
                    BaseAttributeContribution(STAT_HP_BASE, 800.0, SOURCE_CONTEXT),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex(providers, registry=registry),
    )
    events = EventEngine()
    health_runtime = HealthRuntime(
        resolver,
        CharacterHealthStore(
            (
                (CHARACTER, HealthState(1000.0)),
                (CHARACTER_2, HealthState(800.0)),
            )
        ),
        events,
    )
    buff_runtime = BuffRuntime(
        definition_registry=BuffDefinitionRegistry(tuple(definitions)),
        resolver=BuffResolver(),
        buff_store=buff_store,
        event_engine=events,
    )
    coordinator = BuffMaxHpChangeCoordinator(
        buff_port=buff_runtime,
        health_port=health_runtime,
        projection_port=ProjectedBuffMaxHpResolver(resolver, buff_store),
        event_engine=events,
        max_hp_definition_keys=frozenset(
            definition.definition_key
            for definition in definitions
            if any(
                template.target_key == STAT_HP_MAX for template in definition.attribute_modifiers
            )
        ),
    )
    return _World(coordinator, buff_runtime, health_runtime, events, buff_store, resolver)


def _apply(
    request_id: str,
    definition: BuffDefinition,
    frame: int,
    *,
    value: float = 500.0,
    target_ref: AttributeSubjectRef = CHARACTER,
    duration_frames: int = 5,
    order: int = 0,
) -> ApplyBuffRequest:
    return ApplyBuffRequest(
        request_id=request_id,
        frame=frame,
        order=order,
        definition_key=definition.definition_key,
        target_ref=target_ref,
        source_context=SOURCE_CONTEXT,
        duration_frames=duration_frames,
        stack_delta=1,
        modifier_values=(BuffModifierValue(_term_key(definition), value),),
        applier_ref=None,
    )


def _term_key(definition: BuffDefinition) -> str:
    return definition.attribute_modifiers[0].term_key


def _damage(
    amount: float,
    *,
    frame: int,
    change_id: str = "damage:1",
) -> CharacterDamageApplication:
    return CharacterDamageApplication(
        change_id=change_id,
        frame=frame,
        target_ref=CHARACTER,
        amount=amount,
        source_context=SOURCE_CONTEXT,
    )


def test_apply_scales_current_hp_and_publishes_buff_then_max_hp_events():
    definition = _max_hp_definition()
    world = _world(definition)
    world.health_runtime.apply_damage(_damage(400.0, frame=1))
    assert world.health_runtime.get_current_hp(CHARACTER) == 600.0

    world.coordinator.apply(_apply("req:1", definition, 10))

    assert world.health_runtime.get_max_hp(CHARACTER, 10) == 1500.0
    assert world.health_runtime.get_current_hp(CHARACTER) == pytest.approx(900.0)
    assert [event.event_type for event in world.events.frame_events] == [
        EventType.CHARACTER_HEALTH_CHANGED,
        EventType.BUFF_APPLIED,
        EventType.CHARACTER_MAX_HP_CHANGED,
    ]


def test_expiry_restores_ratio_and_publishes_removed_then_max_hp_events():
    definition = _max_hp_definition()
    world = _world(definition)
    world.health_runtime.apply_damage(_damage(400.0, frame=1))
    world.coordinator.apply(_apply("req:1", definition, 10))
    published_before_expiry = len(world.events.frame_events)

    world.coordinator.update_frame(None, 15)

    assert world.health_runtime.get_max_hp(CHARACTER, 15) == 1000.0
    assert world.health_runtime.get_current_hp(CHARACTER) == pytest.approx(600.0)
    assert [event.event_type for event in world.events.frame_events][published_before_expiry:] == [
        EventType.BUFF_REMOVED,
        EventType.CHARACTER_MAX_HP_CHANGED,
    ]


def test_explicit_remove_scales_back():
    definition = _max_hp_definition()
    world = _world(definition)
    world.health_runtime.apply_damage(_damage(400.0, frame=1))
    result = world.coordinator.apply(_apply("req:1", definition, 10))

    world.coordinator.remove(
        RemoveBuffRequest(
            request_id="rm:1",
            frame=12,
            instance_ref=result.instance_ref,
            reason=BuffRemovalReason.EXPLICIT,
        )
    )

    assert world.health_runtime.get_max_hp(CHARACTER, 12) == 1000.0
    assert world.health_runtime.get_current_hp(CHARACTER) == pytest.approx(600.0)


def test_refresh_with_replaced_value_reconciles_delta():
    definition = _max_hp_definition(
        policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
    )
    world = _world(definition)
    world.health_runtime.apply_damage(_damage(500.0, frame=1))
    world.coordinator.apply(_apply("req:1", definition, 10, value=500.0))
    assert world.health_runtime.get_current_hp(CHARACTER) == pytest.approx(750.0)

    world.coordinator.apply(_apply("req:2", definition, 11, value=250.0))

    assert world.health_runtime.get_max_hp(CHARACTER, 11) == 1250.0
    assert world.health_runtime.get_current_hp(CHARACTER) == pytest.approx(625.0)
    assert [event.event_type for event in world.events.frame_events].count(
        EventType.CHARACTER_MAX_HP_CHANGED
    ) == 2


def test_non_max_hp_buff_passthrough_publishes_no_reconcile():
    definition = _atk_definition()
    world = _world(definition)
    world.health_runtime.apply_damage(_damage(400.0, frame=1))

    world.coordinator.apply(_apply("req:1", definition, 10, value=0.2))

    assert world.health_runtime.get_max_hp(CHARACTER, 10) == 1000.0
    assert world.health_runtime.get_current_hp(CHARACTER) == 600.0
    assert [event.event_type for event in world.events.frame_events] == [
        EventType.CHARACTER_HEALTH_CHANGED,
        EventType.BUFF_APPLIED,
    ]


def test_mixed_batch_reconciles_only_max_hp_side():
    atk = _atk_definition()
    max_hp = _max_hp_definition()
    world = _world(atk, max_hp)

    world.coordinator.apply_many(
        (
            _apply("req:1", atk, 10, value=0.2, order=0),
            _apply("req:2", max_hp, 10, value=500.0, order=1),
        )
    )

    assert world.health_runtime.get_max_hp(CHARACTER, 10) == 1500.0
    assert world.health_runtime.get_current_hp(CHARACTER) == pytest.approx(1500.0)
    assert [event.event_type for event in world.events.frame_events].count(
        EventType.CHARACTER_MAX_HP_CHANGED
    ) == 1


def test_target_subject_buff_commits_without_reconcile():
    definition = _max_hp_definition(
        target_kinds=frozenset({AttributeSubjectKind.TARGET}),
    )
    world = _world(definition)

    world.coordinator.apply(_apply("req:1", definition, 10, target_ref=TARGET))

    assert len(world.buff_store.active(10, target_ref=TARGET)) == 1
    assert [event.event_type for event in world.events.frame_events] == [
        EventType.BUFF_APPLIED,
    ]


def test_validation_failure_commits_no_domain():
    definition = _max_hp_definition()
    world = _world(definition)

    class _FailingValidatePort:
        def __init__(self, inner: BuffRuntime) -> None:
            self._inner = inner
            self.definition_registry = inner.definition_registry

        def prepare_apply(self, requests):
            return self._inner.prepare_apply(requests)

        def prepare_expiry(self, frame):
            return self._inner.prepare_expiry(frame)

        def prepare_remove(self, request):
            return self._inner.prepare_remove(request)

        def validate(self, plan):
            raise BuffPlanConflictError("版本冲突")

        def commit_prevalidated(self, plan):
            return self._inner.commit_prevalidated(plan)

        def publish_committed_facts(self, receipt):
            self._inner.publish_committed_facts(receipt)

    failing = BuffMaxHpChangeCoordinator(
        buff_port=_FailingValidatePort(world.buff_runtime),
        health_port=world.health_runtime,
        projection_port=ProjectedBuffMaxHpResolver(
            world.resolver,
            world.buff_store,
        ),
        event_engine=world.events,
        max_hp_definition_keys=frozenset({definition.definition_key}),
    )

    with pytest.raises(BuffPlanConflictError):
        failing.apply(_apply("req:1", definition, 10))

    assert world.buff_store.records == ()
    assert world.health_runtime.get_current_hp(CHARACTER) == 1000.0
    assert world.events.frame_events == ()


def test_coordinator_exposes_max_hp_definition_keys():
    definition = _max_hp_definition()
    world = _world(definition, _atk_definition())

    assert world.coordinator.max_hp_definition_keys == frozenset({definition.definition_key})


def test_reentrant_apply_from_event_raises_reentrancy_error():
    definition = _max_hp_definition()
    atk = _atk_definition()
    world = _world(definition, atk)

    def _reenter(event):
        world.coordinator.apply(_apply("req:reenter", atk, 11, value=0.2))

    world.events.subscribe(EventType.BUFF_APPLIED, _reenter)

    with pytest.raises(BuffMaxHpChangeReentrancyError):
        world.coordinator.apply(_apply("req:1", definition, 10))

    # 外层计划已完整提交并同步；重入请求未产生任何记录。
    assert world.health_runtime.get_max_hp(CHARACTER, 10) == 1500.0
    assert world.health_runtime.get_current_hp(CHARACTER) == pytest.approx(1500.0)
    assert (
        world.buff_store.active(10, target_ref=CHARACTER, definition_key=atk.definition_key)
        == ()
    )


class _DelegatingHealthPort:
    """透传 HealthReconcilePort，供注入准备或提交行为。"""

    def __init__(self, inner: HealthRuntime) -> None:
        self._inner = inner

    def prepare_max_hp_reconcile(
        self,
        character_ref,
        old_max_hp,
        new_max_hp,
        frame,
        *,
        operation_id,
    ):
        return self._inner.prepare_max_hp_reconcile(
            character_ref,
            old_max_hp,
            new_max_hp,
            frame,
            operation_id=operation_id,
        )

    def validate_max_hp_reconcile(self, plan):
        self._inner.validate_max_hp_reconcile(plan)

    def commit_max_hp_reconcile_prevalidated(self, plan):
        return self._inner.commit_max_hp_reconcile_prevalidated(plan)

    def reconcile_events_for(self, receipt):
        return self._inner.reconcile_events_for(receipt)


def test_prevalidated_commit_failure_wraps_as_commit_error():
    definition = _max_hp_definition()
    world = _world(definition)

    class _FailingCommitHealthPort(_DelegatingHealthPort):
        def commit_max_hp_reconcile_prevalidated(self, plan):
            raise RuntimeError("注入的提交故障")

    failing = BuffMaxHpChangeCoordinator(
        buff_port=world.buff_runtime,
        health_port=_FailingCommitHealthPort(world.health_runtime),
        projection_port=ProjectedBuffMaxHpResolver(world.resolver, world.buff_store),
        event_engine=world.events,
        max_hp_definition_keys=frozenset({definition.definition_key}),
    )

    with pytest.raises(BuffMaxHpChangeCommitError):
        failing.apply(_apply("req:1", definition, 10))

    # 契约：Buff Store 先提交且不回滚，事实在两个 Store 完整提交前不发布。
    assert len(world.buff_store.active(10, target_ref=CHARACTER)) == 1
    assert world.health_runtime.get_current_hp(CHARACTER) == 1000.0
    assert world.events.frame_events == ()


def test_multiple_characters_reconcile_in_stable_entity_order():
    definition = _max_hp_definition()
    world = _world(definition)
    reconcile_operation_ids: list[str] = []

    class _RecordingHealthPort(_DelegatingHealthPort):
        def prepare_max_hp_reconcile(
            self,
            character_ref,
            old_max_hp,
            new_max_hp,
            frame,
            *,
            operation_id,
        ):
            reconcile_operation_ids.append(operation_id)
            return super().prepare_max_hp_reconcile(
                character_ref,
                old_max_hp,
                new_max_hp,
                frame,
                operation_id=operation_id,
            )

    coordinator = BuffMaxHpChangeCoordinator(
        buff_port=world.buff_runtime,
        health_port=_RecordingHealthPort(world.health_runtime),
        projection_port=ProjectedBuffMaxHpResolver(world.resolver, world.buff_store),
        event_engine=world.events,
        max_hp_definition_keys=frozenset({definition.definition_key}),
    )

    # 请求顺序 CHARACTER_2 在前（order=0），同步必须按主体稳定排序。
    coordinator.apply_many(
        (
            _apply("req:1", definition, 10, target_ref=CHARACTER_2, value=160.0, order=0),
            _apply("req:2", definition, 10, target_ref=CHARACTER, value=500.0, order=1),
        )
    )

    assert all(op_id.startswith("buff-max-hp:") for op_id in reconcile_operation_ids)
    assert reconcile_operation_ids[0].endswith(CHARACTER.entity_id)
    assert reconcile_operation_ids[1].endswith(CHARACTER_2.entity_id)
    assert world.health_runtime.get_max_hp(CHARACTER, 10) == 1500.0
    assert world.health_runtime.get_max_hp(CHARACTER_2, 10) == 960.0
    assert world.health_runtime.get_current_hp(CHARACTER) == pytest.approx(1500.0)
    assert world.health_runtime.get_current_hp(CHARACTER_2) == pytest.approx(960.0)
    max_hp_results = [
        event.payload.result
        for event in world.events.frame_events
        if event.event_type is EventType.CHARACTER_MAX_HP_CHANGED
        and isinstance(event.payload, CharacterMaxHpChangedPayload)
    ]
    assert [result.target_ref for result in max_hp_results] == [
        CHARACTER,
        CHARACTER_2,
    ]


def test_current_hp_beyond_projected_old_max_hp_commits_nothing():
    definition = _max_hp_definition()
    world = _world(definition)
    # 制造跨领域不一致：当前生命越过投影视图的旧最大生命，比例结果会
    # 越过新最大生命，由生命值领域校验拦截并原样上抛。
    world.health_runtime.character_health_store.require(CHARACTER).current_hp = 1200.0

    with pytest.raises(InvalidCurrentHealthError):
        world.coordinator.apply(_apply("req:1", definition, 10))

    assert world.buff_store.records == ()
    assert world.health_runtime.get_current_hp(CHARACTER) == 1200.0
    assert world.events.frame_events == ()
