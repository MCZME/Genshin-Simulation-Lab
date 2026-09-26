"""通用能量回能判定组件单元测试。

对齐通用回能机制规则（维护者 2026-09-25 提供）：触发标签词表、按武器类型的
初始概率与失败递增、概率封顶、成功恢复 1 点并重置、切人不重置、后台不判定、
每角色独立。数值与概率阶梯全部为规则表直出（见测试规范 §3.2，合成驱动）；
需要随机结果的分支用种子搜索选取确定的首取样序列。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.contracts.intents import IntentKind
from genshin_sim.core.entity_states.energy import EnergyState
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.random_source import RandomSource
from genshin_sim.core.systems.energy import (
    ENERGY_RECOVERY_RULES_BY_WEAPON_TYPE,
    CharacterEnergyProfile,
    CharacterEnergyStore,
    EnergyElement,
    EnergyRecoveryRule,
    EnergyRecoveryStage,
    EnergyRecoveryStore,
    is_energy_recovery_trigger_tag,
    recovery_rule_for_weapon_type,
)
from genshin_sim.core.systems.energy.errors import (
    EnergyRecoveryError,
    EnergyValidationError,
)
from tests.helpers.events import make_damage_resolved_event, make_event_context

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


def _seed_whose_first_draws_fail(*thresholds: float) -> int:
    """选取前 N 次取样全部不低于阈值的种子，让概率阶梯判定全部失败。"""

    for seed in range(100_000):
        source = RandomSource(seed)
        if all(source.next() >= threshold for threshold in thresholds):
            return seed
    raise AssertionError("未找到满足阈值序列的随机种子")


def _seed_whose_first_draw_succeeds(threshold: float) -> int:
    """选取首取样低于阈值的种子，让首次判定成功。"""

    for seed in range(100_000):
        if RandomSource(seed).next() < threshold:
            return seed
    raise AssertionError("未找到成功判定的随机种子")


def test_rules_table_matches_weapon_type_baseline():
    assert {
        "sword": EnergyRecoveryRule(0.10, 0.05),
        "claymore": EnergyRecoveryRule(0.00, 0.10),
        "polearm": EnergyRecoveryRule(0.00, 0.04),
        "catalyst": EnergyRecoveryRule(0.00, 0.10),
        "bow": EnergyRecoveryRule(0.00, 0.05),
    } == ENERGY_RECOVERY_RULES_BY_WEAPON_TYPE


def test_unknown_weapon_type_fails_at_lookup():
    with pytest.raises(EnergyValidationError):
        recovery_rule_for_weapon_type("magic")


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("普通攻击1", True),
        ("普通攻击4", True),
        ("重击", True),
        ("元素战技", False),
        ("元素爆发", False),
        ("下落攻击", False),
        ("星超导冰", False),
        ("星扩散冰", False),
        ("", False),
        (None, False),
    ],
)
def test_trigger_tag_vocabulary(tag, expected):
    assert is_energy_recovery_trigger_tag(tag) is expected


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

    with pytest.raises(EnergyRecoveryError):
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


def test_recovery_store_rejects_duplicate_and_foreign_refs():
    with pytest.raises(EnergyValidationError):
        EnergyRecoveryStore(
            (
                (REF_1, recovery_rule_for_weapon_type("sword")),
                (
                    AttributeSubjectRef.character("character:slot_1"),
                    recovery_rule_for_weapon_type("bow"),
                ),
            )
        )

    store = _recovery_store()
    with pytest.raises(LookupError):
        store.next_probability(AttributeSubjectRef.character("character:slot_3"))
