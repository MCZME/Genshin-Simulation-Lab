from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.elements import (
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.reaction import (
    CrystallizeShardLifecycleState,
    CrystallizeShardState,
    CrystallizeShardStateCreationIntent,
    CrystallizeSourceObservation,
    ReactionRegistry,
    ReactionRuntime,
    ReactionStateInstanceRef,
    ReactionStateScopeKey,
)
from genshin_sim.core.systems.reaction.mechanics.crystallize import crystallize_definition
from genshin_sim.core.systems.reaction.mechanics.crystallize.formulas import (
    capture_crystallize_shield_basis,
)

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")


def test_crystallize_shard_state_uses_its_deterministic_scope_and_runtime_index():
    runtime = ReactionRuntime(ReactionRegistry((crystallize_definition(),)))
    occurrence_ref = "interaction:crystallize:occurrence:0"
    instance_ref = ReactionStateInstanceRef(f"reaction-state:crystallize-shard:{occurrence_ref}")
    intent = CrystallizeShardStateCreationIntent(
        "intent:crystallize",
        occurrence_ref,
        instance_ref,
        TARGET,
        f"reaction_object:crystallize_shard:{occurrence_ref}",
        Element.PYRO,
        SOURCE,
        capture_crystallize_shield_basis(
            CrystallizeSourceObservation(SOURCE, 90, 0),
            captured_frame=0,
        ),
        0,
        900,
    )
    planner = runtime.begin_state_batch(0, "crystallize")
    shard = planner.create_crystallize_shard(intent)
    receipt = runtime.commit_prevalidated_state_plan(planner.seal())

    assert isinstance(shard, CrystallizeShardState)
    assert shard.slot_key.scope_key == ReactionStateScopeKey(instance_ref.value)
    assert shard.next_required_frame == 900
    assert runtime.crystallize_shard_state_for(instance_ref) == shard
    assert runtime.next_required_frame() == 900
    assert receipt.version == 1
    snapshot = cast(list[dict[str, object]], runtime.snapshot(0).to_dict()["state_records"])
    assert snapshot[0]["space_entity_ref"] == shard.space_entity_ref
    assert snapshot[0]["lifecycle_state"] == "active"


def test_crystallize_shard_state_rejects_identity_not_derived_from_its_occurrence():
    occurrence_ref = "interaction:crystallize:occurrence:0"
    basis = capture_crystallize_shield_basis(
        CrystallizeSourceObservation(SOURCE, 90, 0),
        captured_frame=0,
    )

    with pytest.raises(ValueError, match="instance_ref 必须由 occurrence_ref 确定性派生"):
        CrystallizeShardState(
            ReactionStateInstanceRef("reaction-state:crystallize-shard:other"),
            TARGET,
            f"reaction_object:crystallize_shard:{occurrence_ref}",
            Element.PYRO,
            occurrence_ref,
            SOURCE,
            basis,
            0,
            900,
        )

    with pytest.raises(ValueError, match="space_entity_ref 必须由 occurrence_ref 确定性派生"):
        CrystallizeShardState(
            ReactionStateInstanceRef(f"reaction-state:crystallize-shard:{occurrence_ref}"),
            TARGET,
            "reaction_object:crystallize_shard:other",
            Element.PYRO,
            occurrence_ref,
            SOURCE,
            basis,
            0,
            900,
        )


def test_crystallize_shard_state_terminalization_keeps_a_tombstone_outside_required_frame():
    runtime = ReactionRuntime(ReactionRegistry((crystallize_definition(),)))
    occurrence_ref = "interaction:crystallize:occurrence:terminal"
    instance_ref = ReactionStateInstanceRef(f"reaction-state:crystallize-shard:{occurrence_ref}")
    intent = CrystallizeShardStateCreationIntent(
        "intent:crystallize:terminal",
        occurrence_ref,
        instance_ref,
        TARGET,
        f"reaction_object:crystallize_shard:{occurrence_ref}",
        Element.PYRO,
        SOURCE,
        capture_crystallize_shield_basis(
            CrystallizeSourceObservation(SOURCE, 90, 0),
            captured_frame=0,
        ),
        0,
        900,
    )
    create = runtime.begin_state_batch(0, "crystallize:terminal:create")
    shard = create.create_crystallize_shard(intent)
    runtime.commit_prevalidated_state_plan(create.seal())
    runtime.update_frame(None, 1)

    terminalize = runtime.begin_state_batch(1, "crystallize:terminal:pick")
    picked = terminalize.terminalize_crystallize_shard(
        instance_ref=instance_ref,
        lifecycle_state=CrystallizeShardLifecycleState.PICKED,
    )
    runtime.commit_prevalidated_state_plan(terminalize.seal())

    assert picked.lifecycle_state is CrystallizeShardLifecycleState.PICKED
    assert picked.terminal_frame == 1
    assert picked.revision == shard.revision + 1
    assert picked.next_required_frame is None
    assert runtime.crystallize_shard_state_for(instance_ref) == picked
    assert runtime.is_idle()

    retry = runtime.begin_state_batch(1, "crystallize:terminal:retry")
    with pytest.raises(ValueError, match="已经处于终态"):
        retry.terminalize_crystallize_shard(
            instance_ref=instance_ref,
            lifecycle_state=CrystallizeShardLifecycleState.PICKED,
        )
