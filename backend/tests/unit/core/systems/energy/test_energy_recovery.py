"""通用能量回能判定组件单元测试。

对齐通用回能机制规则：按武器类型的
初始概率与失败递增、概率封顶、成功恢复 1 点并重置、切人不重置、后台不判定、
每角色独立、帧游标按序消费。数值与概率阶梯全部为规则表直出（见测试规范 §3.2，
合成驱动）；需要随机结果的分支用种子搜索选取确定的首取样序列。
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.contracts.intents import IntentKind
from genshin_sim.core.entity_states.energy import EnergyState
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.random_source import RandomSource
from genshin_sim.core.systems.energy import (
    CharacterEnergyProfile,
    CharacterEnergyStore,
    EnergyElement,
    EnergyRecoveryRule,
    EnergyRecoveryStage,
    EnergyRecoveryStore,
    recovery_rule_for_weapon_type,
)
from genshin_sim.core.systems.energy.errors import (
    CharacterEnergyNotFoundError,
    EnergyRecoveryError,
    EnergyValidationError,
)
from tests.helpers.events import (
    make_damage_resolved_event,
    make_event_context,
    make_reaction_occurrence_event,
)

if TYPE_CHECKING:
    from genshin_sim.core.simulation.intent_queue import IntentQueue
    from genshin_sim.core.systems.energy.runtime import TeamReadPort

REF_1 = AttributeSubjectRef.character("character:slot_1")
REF_2 = AttributeSubjectRef.character("character:slot_2")
CAPACITY = 100.0


class _IntentQueueStub:
    def __init__(self) -> None:
        self.enqueued: list = []

    def enqueue(self, intent) -> None:
        self.enqueued.append(intent)


def _team_state(active_slot: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        active_slot=active_slot,
        characters=(
            SimpleNamespace(slot=1, combat_entity_id="character:slot_1"),
            SimpleNamespace(slot=2, combat_entity_id="character:slot_2"),
        ),
    )


def _energy_store(
    capacity_by_ref: dict[AttributeSubjectRef, float] | None = None,
) -> CharacterEnergyStore:
    capacities = capacity_by_ref or {REF_1: CAPACITY, REF_2: CAPACITY}
    return CharacterEnergyStore(
        (
            CharacterEnergyProfile(ref, ref.entity_id, EnergyElement.CRYO, capacity),
            EnergyState(0.0),
        )
        for ref, capacity in capacities.items()
    )


def _recovery_store(
    rules: dict[AttributeSubjectRef, EnergyRecoveryRule] | None = None,
) -> EnergyRecoveryStore:
    entries = rules or {
        REF_1: recovery_rule_for_weapon_type("claymore"),
        REF_2: recovery_rule_for_weapon_type("sword"),
    }
    return EnergyRecoveryStore(entries.items())


def _stage(
    queue: _IntentQueueStub,
    *,
    rules: dict[AttributeSubjectRef, EnergyRecoveryRule] | None = None,
    capacity_by_ref: dict[AttributeSubjectRef, float] | None = None,
    active_slot: int = 1,
    team_state: SimpleNamespace | None = None,
) -> tuple[EnergyRecoveryStage, EnergyRecoveryStore]:
    recovery_store = _recovery_store(rules)
    stage = EnergyRecoveryStage(
        recovery_store,
        _energy_store(capacity_by_ref=capacity_by_ref),
        cast("TeamReadPort", team_state or _team_state(active_slot)),
        cast("IntentQueue", queue),
    )
    return stage, recovery_store


def _judgment(
    stage: EnergyRecoveryStage,
    request_id: str,
    *,
    tag: str = "重击",
    source_key: str = "character:slot_1",
    frame: int = 10,
    random_source: RandomSource | None = None,
) -> None:
    context = make_event_context(
        frame,
        (
            make_damage_resolved_event(
                frame,
                request_id,
                source_key=source_key,
                main_attack_tag=tag,
            ),
        ),
        random_source=random_source,
    )
    stage.update_frame(context, frame)


def _seed_whose_draws_match(*matches: Callable[[float], bool]) -> int:
    """选取前 N 次取样依次满足条件的随机种子。"""

    for seed in range(100_000):
        source = RandomSource(seed)
        if all(match(source.next()) for match in matches):
            return seed
    raise AssertionError("未找到满足取样序列的随机种子")


def _seed_whose_first_draws_fail(*thresholds: float) -> int:
    """选取前 N 次取样全部不低于阈值的种子，让概率阶梯判定全部失败。"""

    return _seed_whose_draws_match(
        *(lambda value, bound=threshold: value >= bound for threshold in thresholds)
    )


def _seed_whose_first_draw_succeeds(threshold: float) -> int:
    """选取首取样低于阈值的种子，让首次判定成功。"""

    return _seed_whose_draws_match(lambda value: value < threshold)


def test_store_failure_ladder_accumulates_caps_and_success_resets():
    # 双手剑初始 0%：每次失败 +10%，封顶 100%；成功重置回初始值。
    store = _recovery_store()

    for index in range(10):
        store.record_failure(REF_1)
        assert store.next_probability(REF_1) == pytest.approx((index + 1) * 0.1)

    # 已封顶后继续失败不再越界。
    store.record_failure(REF_1)
    assert store.next_probability(REF_1) == pytest.approx(1.0)

    store.record_success(REF_1)
    assert store.next_probability(REF_1) == pytest.approx(0.0)


def test_first_claymore_judgment_fails_without_consuming_random_source():
    # 初始概率 0：判定必然失败，且不消耗随机序列（roll(0) 确定短路）。
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(queue)
    random_source = RandomSource(7)

    _judgment(stage, "damage:1", random_source=random_source)

    assert queue.enqueued == []
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.1)
    assert random_source.draw_count == 0


def test_success_judgment_restores_one_point_and_resets():
    # 单手剑初始 10%：选首取样 < 0.1 的种子让首次判定成功——产出下一轮结算
    # 消费的 1 点能量恢复请求，概率重置回初始值。
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(
        queue,
        rules={REF_1: recovery_rule_for_weapon_type("sword")},
    )

    _judgment(
        stage,
        "damage:1",
        tag="普通攻击1",
        random_source=RandomSource(_seed_whose_first_draw_succeeds(0.10)),
    )

    assert len(queue.enqueued) == 1
    envelope = queue.enqueued[0]
    assert envelope.kind is IntentKind.IMPACT
    assert envelope.source_ref == "energy.recovery"
    payload = cast(ImpactRequest, envelope.payload)
    assert payload.kind is ImpactKind.ENERGY
    assert payload.impact_key == "energy.recovery.restore"
    assert payload.owner_slot == 1
    assert payload.target_refs == ("character:slot_1",)
    request_id = payload.request_id
    assert request_id is not None and request_id.startswith("energy.recovery:damage:1:")
    energy = cast(dict, payload.params["energy"])
    assert energy["schema_version"] == 1
    assert energy["operation"] == "restore"
    assert energy["amount"] == 1.0
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.10)


def test_failed_judgment_accumulates_probability():
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(
        queue,
        rules={REF_1: recovery_rule_for_weapon_type("sword")},
    )

    _judgment(
        stage,
        "damage:1",
        random_source=RandomSource(_seed_whose_first_draws_fail(0.10)),
    )

    assert queue.enqueued == []
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.15)


def test_missing_random_source_fails_judgment():
    # 判定发生时缺随机源属于装配契约破坏：即使概率为 0 也在判定点显式失败，
    # 不静默跳过。
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(queue)

    with pytest.raises(EnergyRecoveryError, match="缺少装配期注入的仿真随机源"):
        _judgment(stage, "damage:1")

    assert queue.enqueued == []
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.0)


def test_off_field_attack_neither_rolls_nor_accumulates():
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(
        queue,
        rules={REF_1: recovery_rule_for_weapon_type("sword")},
        active_slot=2,
    )
    random_source = RandomSource(7)

    _judgment(stage, "damage:1", random_source=random_source)

    assert queue.enqueued == []
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.10)
    assert random_source.draw_count == 0


def test_probability_survives_swap_and_judgment_continues_on_return():
    # 切人不重置：场上累积 3 次失败到 0.25，切下场后无判定；回到场上后下一
    # 次判定从 0.25 继续递增到 0.3。阈值取略高于累积值，规避浮点边界。
    seed = _seed_whose_first_draws_fail(0.11, 0.16, 0.21, 0.26)
    queue = _IntentQueueStub()
    team_state = _team_state()
    stage, recovery_store = _stage(
        queue,
        rules={REF_1: recovery_rule_for_weapon_type("sword")},
        team_state=team_state,
    )
    random_source = RandomSource(seed)

    for index in range(3):
        _judgment(
            stage,
            f"damage:{index}",
            frame=10 + index,
            random_source=random_source,
        )
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.25)

    team_state.active_slot = 2
    _judgment(stage, "damage:offfield", frame=20, random_source=random_source)
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.25)
    assert queue.enqueued == []

    team_state.active_slot = 1
    _judgment(stage, "damage:return", frame=30, random_source=random_source)
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.30)


def test_per_character_probability_is_independent():
    store = _recovery_store()
    store.record_failure(REF_1)
    store.record_failure(REF_1)

    assert store.next_probability(REF_1) == pytest.approx(0.20)
    assert store.next_probability(REF_2) == pytest.approx(0.10)


def test_non_trigger_tags_do_not_consume_random_source():
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(
        queue,
        rules={REF_1: recovery_rule_for_weapon_type("sword")},
    )
    random_source = RandomSource(7)

    for tag in ("元素战技", "元素爆发", "星超导冰", "下落攻击"):
        _judgment(stage, "damage:1", tag=tag, random_source=random_source)

    assert queue.enqueued == []
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.10)
    assert random_source.draw_count == 0


def test_same_frame_events_are_judged_in_event_order():
    # 同帧两条伤害事实按事件顺序各判定一次：第一条失败累积到 0.15，第二条
    # 成功重置回 0.10；成功请求携带第二条事实的 request_id 与事件序号。
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(
        queue,
        rules={REF_1: recovery_rule_for_weapon_type("sword")},
    )
    random_source = RandomSource(
        _seed_whose_draws_match(
            lambda value: value >= 0.10,
            lambda value: value < 0.15,
        )
    )
    context = make_event_context(
        10,
        (
            make_damage_resolved_event(10, "damage:a", main_attack_tag="重击"),
            make_damage_resolved_event(10, "damage:b", main_attack_tag="重击"),
        ),
        random_source=random_source,
    )

    stage.update_frame(context, 10)

    assert random_source.draw_count == 2
    assert len(queue.enqueued) == 1
    payload = cast(ImpactRequest, queue.enqueued[0].payload)
    assert payload.request_id == "energy.recovery:damage:b:10:1"
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.10)


def test_repeated_update_frame_in_same_frame_does_not_reconsume():
    # 帧游标推进后，同一帧重复调用 update_frame 不重复消费事实。
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(
        queue,
        rules={REF_1: recovery_rule_for_weapon_type("sword")},
    )
    random_source = RandomSource(_seed_whose_first_draws_fail(0.10))
    context = make_event_context(
        10,
        (make_damage_resolved_event(10, "damage:a", main_attack_tag="重击"),),
        random_source=random_source,
    )

    stage.update_frame(context, 10)
    stage.update_frame(context, 10)

    assert random_source.draw_count == 1
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.15)
    assert queue.enqueued == []


def test_only_damage_resolved_events_with_results_are_judged():
    # 非 DAMAGE_RESOLVED 事件与无结算结果的事实直接跳过，不消耗随机序列；
    # 同帧的合法伤害事实仍被正常判定。
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(
        queue,
        rules={REF_1: recovery_rule_for_weapon_type("sword")},
    )
    random_source = RandomSource(_seed_whose_first_draw_succeeds(0.10))
    context = make_event_context(
        10,
        (
            make_reaction_occurrence_event(10, "reaction:electro_charged", "occurrence:1"),
            SimpleNamespace(
                event_type=EventType.DAMAGE_RESOLVED,
                payload=SimpleNamespace(result=None),
            ),
            make_damage_resolved_event(10, "damage:a", main_attack_tag="重击"),
        ),
        random_source=random_source,
    )

    stage.update_frame(context, 10)

    assert random_source.draw_count == 1
    assert len(queue.enqueued) == 1
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.10)


def test_capped_probability_succeeds_without_consuming_random_source():
    # 概率封顶 100%：roll(1) 确定成功且不消耗随机序列，恢复后概率重置。
    # 浮点累积下 10 次 +0.1 只到 0.9999999999999999，第 11 次失败才被钳到精确 1.0。
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(queue)
    random_source = RandomSource(7)

    for _ in range(11):
        recovery_store.record_failure(REF_1)
    assert recovery_store.next_probability(REF_1) == 1.0

    _judgment(stage, "damage:1", random_source=random_source)

    assert random_source.draw_count == 0
    assert len(queue.enqueued) == 1
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.0)


def test_stage_is_idle_regardless_of_judgment_activity():
    # 回能判定不延长仿真：阶段在任何状态下都报告空闲。
    queue = _IntentQueueStub()
    stage, _ = _stage(queue)

    assert stage.is_idle() is True

    _judgment(stage, "damage:1", random_source=RandomSource(_seed_whose_first_draws_fail(0.10)))

    assert stage.is_idle() is True


def test_capacity_zero_character_is_not_judged():
    queue = _IntentQueueStub()
    stage, recovery_store = _stage(
        queue,
        rules={REF_1: recovery_rule_for_weapon_type("sword")},
        capacity_by_ref={REF_1: 0.0, REF_2: CAPACITY},
    )
    random_source = RandomSource(7)

    _judgment(stage, "damage:1", random_source=random_source)

    assert queue.enqueued == []
    assert recovery_store.next_probability(REF_1) == pytest.approx(0.10)
    assert random_source.draw_count == 0


def test_recovery_store_rejects_duplicate_character_refs():
    with pytest.raises(EnergyValidationError, match="角色通用回能主体重复"):
        EnergyRecoveryStore(
            (
                (REF_1, recovery_rule_for_weapon_type("sword")),
                (
                    AttributeSubjectRef.character("character:slot_1"),
                    recovery_rule_for_weapon_type("bow"),
                ),
            )
        )


def test_recovery_store_unknown_character_lookup_fails():
    store = _recovery_store()

    with pytest.raises(CharacterEnergyNotFoundError, match="角色通用回能判定状态不存在"):
        store.next_probability(AttributeSubjectRef.character("character:slot_3"))
