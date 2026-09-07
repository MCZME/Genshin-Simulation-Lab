from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    BurningStateLinkBatchCoordinator,
    ElementalStateLinkConflictError,
    validate_burning_state_links,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraDecayMode,
    AuraRuntime,
    AuraStateLinkMutationRequest,
    AuraStrength,
    BurningAuraApplicationRequest,
)
from genshin_sim.core.systems.reaction import (
    BurningCycleRootWork,
    BurningState,
    ReactionStateInstanceRef,
    ReactionStateSlot,
    ReactionStateSlotKey,
    ScheduledStateTickCause,
    ScheduledStateTickKind,
    create_default_reaction_bootstrap,
)
from tests.helpers.reactions import burning_basis

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")
LINK = ElementalStateLinkRef("elemental-state-link:test")


def test_burning_cycle_root_derives_independent_damage_and_pyro_causes():
    instance_ref = ReactionStateInstanceRef("reaction-state-instance:burning")
    root = BurningCycleRootWork(
        work_id=(
            "reaction-state:reaction-state-instance:burning:frame:15:"
            "burning:damage:2:pyro_application:1"
        ),
        frame=15,
        root_order=0,
        state_instance_ref=instance_ref,
        subject_ref=TARGET,
        damage_tick_index=2,
        pyro_application_index=1,
    )

    assert root.state_slot is ReactionStateSlot.BURNING
    assert tuple(cause.tick_kind for cause in root.causes) == (
        ScheduledStateTickKind.BURNING_DAMAGE,
        ScheduledStateTickKind.BURNING_PYRO_APPLICATION,
    )
    assert tuple(cause.tick_index for cause in root.causes) == (2, 1)

    with pytest.raises(ValueError, match="damage_cause 必须与 root identity 一致"):
        BurningCycleRootWork(
            work_id=(
                "reaction-state:reaction-state-instance:burning:frame:15:"
                "burning:damage:2:pyro_application:1"
            ),
            frame=15,
            root_order=0,
            state_instance_ref=instance_ref,
            subject_ref=TARGET,
            damage_tick_index=2,
            pyro_application_index=1,
            damage_cause=ScheduledStateTickCause(
                state_instance_ref=instance_ref,
                scheduled_frame=15,
                tick_kind=ScheduledStateTickKind.BURNING_DAMAGE,
                tick_index=3,
            ),
        )

    damage_only = BurningCycleRootWork(
        work_id=(
            "reaction-state:reaction-state-instance:burning:frame:30:"
            "burning:damage:3:pyro_application:0"
        ),
        frame=30,
        root_order=1,
        state_instance_ref=instance_ref,
        subject_ref=TARGET,
        damage_tick_index=3,
    )
    pyro_only = BurningCycleRootWork(
        work_id=(
            "reaction-state:reaction-state-instance:burning:frame:120:"
            "burning:damage:0:pyro_application:2"
        ),
        frame=120,
        root_order=2,
        state_instance_ref=instance_ref,
        subject_ref=TARGET,
        pyro_application_index=2,
    )

    assert damage_only.scheduled_tick_index == 3
    assert damage_only.causes == (damage_only.damage_cause,)
    assert pyro_only.scheduled_tick_index == 2
    assert pyro_only.causes == (pyro_only.pyro_cause,)


def test_burning_state_tracks_shared_link_source_and_independent_cycle_cursors():
    runtime = create_default_reaction_bootstrap().create_runtime()
    planner = runtime.begin_state_batch(0, "burning-create")
    created = planner.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=burning_basis(),
        next_dendro_like_depletion_frame=300,
        next_damage_tick_frame=15,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    assert isinstance(created, BurningState)
    assert created.slot_key == ReactionStateSlotKey(TARGET, ReactionStateSlot.BURNING)
    assert created.next_required_frame == 15
    assert runtime.burning_state_for(TARGET) == created
    assert runtime.next_required_frame() == 15
    snapshot = cast(list[dict[str, object]], runtime.snapshot(0).to_dict()["state_records"])
    assert snapshot == [
        {
            "slot": "burning",
            "scope_key": "shared",
            "subject": {"kind": "target", "entity_id": "target:target_1"},
            "instance_ref": created.instance_ref.value,
            "next_required_frame": 15,
            "burning_aura_link_ref": LINK.link_key,
            "dendro_like_link_refs": [LINK.link_key],
            "created_frame": 0,
            "created_by_occurrence_ref": "interaction:burning:occurrence:0",
            "current_effect_owner": SOURCE.to_dict(),
            "captured_scaling_basis": {
                "basis_ref": burning_basis().basis_ref,
                "captured_frame": 0,
                "source_ref": SOURCE.to_dict(),
                "source_kind": "character",
                "source_level": 90,
                "elemental_mastery": 120.0,
                "reaction_bonus": 0.0,
                "reaction_profile_key": "reaction_profile.burning.incoming_pyro_on_dendro",
                "damage_profile_key": "damage_profile.reaction.burning",
                "level_multiplier_table_key": "character",
                "level_multiplier": 1446.853,
                "source_observation_ref": "observation:burning:character:slot_1:0",
                "source_owner_slot": 1,
            },
            "next_dendro_like_depletion_frame": 300,
            "next_damage_tick_frame": 15,
            "next_damage_tick_index": 2,
            "next_pyro_application_frame": 15,
            "next_pyro_application_index": 1,
            "revision": 1,
        }
    ]


def test_burning_state_depletion_frame_is_a_runtime_required_frame():
    runtime = create_default_reaction_bootstrap().create_runtime()
    planner = runtime.begin_state_batch(0, "burning-depletion-frame")
    planner.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=burning_basis(),
        next_dendro_like_depletion_frame=10,
        next_damage_tick_frame=15,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    assert runtime.next_required_frame() == 10
    with pytest.raises(ValueError, match="不能跨过 ReactionState 必需处理帧"):
        runtime.update_frame(None, 11)


def test_burning_state_source_refresh_preserves_identity_and_cannot_reset_cursors():
    runtime = create_default_reaction_bootstrap().create_runtime()
    create = runtime.begin_state_batch(0, "burning-create")
    created = create.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=burning_basis(),
        next_dendro_like_depletion_frame=300,
        next_damage_tick_frame=15,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    runtime.commit_prevalidated_state_plan(create.seal())

    refreshed_source = ElementalSourceRef("character:slot_2")
    refresh = runtime.begin_state_batch(0, "burning-refresh")
    refreshed = refresh.replace_burning(
        replace(
            created,
            current_effect_owner=refreshed_source,
            captured_scaling_basis=burning_basis(refreshed_source),
            revision=created.revision + 1,
        )
    )
    runtime.commit_prevalidated_state_plan(refresh.seal())

    assert refreshed.instance_ref == created.instance_ref
    assert refreshed.burning_aura_link_ref == created.burning_aura_link_ref
    assert refreshed.dendro_like_link_refs == created.dendro_like_link_refs
    assert refreshed.next_dendro_like_depletion_frame == created.next_dendro_like_depletion_frame
    assert refreshed.next_damage_tick_frame == created.next_damage_tick_frame
    assert refreshed.next_damage_tick_index == created.next_damage_tick_index
    assert refreshed.next_pyro_application_frame == created.next_pyro_application_frame
    assert refreshed.next_pyro_application_index == created.next_pyro_application_index
    assert refreshed.current_effect_owner == refreshed_source

    invalid_refresh = runtime.begin_state_batch(0, "burning-invalid-refresh")
    with pytest.raises(ValueError, match="不能回退周期 cursor"):
        invalid_refresh.replace_burning(
            replace(
                refreshed,
                next_damage_tick_frame=16,
                next_damage_tick_index=1,
                revision=refreshed.revision + 1,
            )
        )


def test_burning_state_link_validator_requires_burning_and_dendro_complete_projection():
    aura_runtime = AuraRuntime()
    aura_runtime.apply(
        AuraApplicationRequest(
            "aura:dendro",
            "aura:dendro:application",
            "impact:dendro",
            0,
            0,
            SOURCE,
            TARGET,
            Element.DENDRO,
            AuraStrength.WEAK,
        )
    )
    reaction_runtime = create_default_reaction_bootstrap().create_runtime()
    aura_planner = aura_runtime.begin_batch(0, "burning-link")
    aura_planner.mutate_state_links(
        AuraStateLinkMutationRequest(
            "aura:dendro:burning-link",
            0,
            0,
            TARGET,
            AuraKind.DENDRO,
            add_link_refs=(LINK,),
            decay_mode=AuraDecayMode.REACTION_MANAGED,
        )
    )
    aura_planner.apply_burning(
        BurningAuraApplicationRequest(
            "aura:burning",
            "aura:burning:application",
            "impact:burning",
            0,
            1,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(2),
        )
    )
    state_planner = reaction_runtime.begin_state_batch(0, "burning-link")
    state = state_planner.create_burning(
        subject_ref=TARGET,
        burning_aura_link_ref=LINK,
        dendro_like_link_refs=(LINK,),
        created_by_occurrence_ref="interaction:burning:occurrence:0",
        current_effect_owner=SOURCE,
        captured_scaling_basis=burning_basis(),
        next_dendro_like_depletion_frame=300,
        next_damage_tick_frame=15,
        next_damage_tick_index=2,
        next_pyro_application_frame=15,
        next_pyro_application_index=1,
    )
    receipt = BurningStateLinkBatchCoordinator(
        aura_runtime,
        reaction_runtime,
    ).commit_prevalidated(aura_planner.seal(), state_planner.seal())

    validate_burning_state_links(
        aura_runtime.snapshot().targets,
        reaction_runtime.state_snapshot(0).records,
    )
    assert receipt.reaction_state_receipt.plan.replacement_records == (state,)

    extra_link = ElementalStateLinkRef("elemental-state-link:extra")
    extra_link_plan = aura_runtime.begin_batch(0, "burning-extra-link")
    extra_link_plan.mutate_state_links(
        AuraStateLinkMutationRequest(
            "aura:dendro:extra-link",
            0,
            0,
            TARGET,
            AuraKind.DENDRO,
            add_link_refs=(extra_link,),
        )
    )
    aura_runtime.commit_prevalidated(extra_link_plan.seal())

    with pytest.raises(
        ElementalStateLinkConflictError,
        match="BurningState 的类草 Link 与 Aura 不一致",
    ):
        validate_burning_state_links(
            aura_runtime.snapshot().targets,
            reaction_runtime.state_snapshot(0).records,
        )
