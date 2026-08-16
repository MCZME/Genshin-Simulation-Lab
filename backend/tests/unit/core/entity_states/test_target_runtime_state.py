from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.core.entity_states import TargetRuntimeCollection, TargetRuntimeState


def test_target_runtime_state_builds_default_spatial_entity_id_and_copies_resistance():
    resistance = {"pyro": 0.1}

    target = TargetRuntimeState(
        target_id="target_1",
        level=90,
        resistance=resistance,
    )
    resistance["pyro"] = 0.5

    assert target.spatial_entity_id == "target:target_1"
    assert target.resistance == {"pyro": 0.1}


def test_target_runtime_collection_indexes_targets_by_target_and_space_id():
    first = TargetRuntimeState(target_id="target_1")
    second = TargetRuntimeState(target_id="target_2", spatial_entity_id="target:custom")
    targets = TargetRuntimeCollection([first, second])

    assert len(targets) == 2
    assert targets.target_ids == ("target_1", "target_2")
    assert targets.targets == (first, second)
    assert targets.get("target_1") is first
    assert targets.get("missing") is None
    assert targets.get_by_spatial_entity_id("target:custom") is second
    assert targets.get_by_spatial_entity_id("target:missing") is None


@pytest.mark.parametrize(
    ("target", "message"),
    [
        (TargetRuntimeState(target_id="target_1"), "目标 id 重复：target_1"),
        (
            TargetRuntimeState(target_id="target_2", spatial_entity_id="target:target_1"),
            "目标空间实体 id 重复：target:target_1",
        ),
    ],
)
def test_target_runtime_collection_rejects_duplicate_identity(
    target: TargetRuntimeState,
    message: str,
):
    with pytest.raises(ValueError, match=message):
        TargetRuntimeCollection([TargetRuntimeState(target_id="target_1"), target])


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"target_id": ""}, "目标 id 必须是非空字符串"),
        ({"target_id": "target_1", "level": 0}, "目标等级必须是正整数"),
        (
            {"target_id": "target_1", "resistance": {"": 0.1}},
            "目标抗性名称必须是非空字符串",
        ),
    ],
)
def test_target_runtime_state_validates_minimum_fields(
    kwargs: dict[str, object],
    message: str,
):
    with pytest.raises(ValueError, match=message):
        TargetRuntimeState(**cast(Any, kwargs))
