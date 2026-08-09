from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.coordination.elemental_reaction import (
    ElementalStateLinkConflictError,
    FrozenStateLinkBatchCoordinator,
    validate_frozen_state_links,
)
from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraRuntime,
    AuraStrength,
    FrozenAuraApplicationRequest,
)
from genshin_sim.core.systems.reaction import (
    FreezeRecoveryState,
    create_default_reaction_bootstrap,
)

SOURCE = ElementalSourceRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")
LINK = ElementalStateLinkRef("elemental-state-link:test")


def test_freeze_recovery_state_is_not_an_active_frozen_state_or_link_participant():
    runtime = create_default_reaction_bootstrap().create_runtime()
    runtime.update_frame(None, 20)
    planner = runtime.begin_state_batch(20, "recovery")
    recovery = planner.create_freeze_recovery(
        subject_ref=TARGET,
        decay_rate=0.6,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    assert isinstance(recovery, FreezeRecoveryState)
    assert recovery.next_required_frame is None
    assert runtime.frozen_state_for(TARGET) is None
    assert runtime.freeze_recovery_state_for(TARGET) == recovery
    assert runtime.is_idle()
    snapshot_record = cast(
        list[dict[str, object]], runtime.snapshot(20).to_dict()["state_records"]
    )[0]
    assert snapshot_record["slot"] == "freeze_recovery"
    assert "state_link_ref" not in snapshot_record


def test_frozen_state_tracks_decay_rate_and_its_update_frame():
    runtime = create_default_reaction_bootstrap().create_runtime()
    runtime.update_frame(None, 12)
    planner = runtime.begin_state_batch(12, "frozen-rate")
    frozen = planner.create_frozen(
        subject_ref=TARGET,
        state_link_ref=LINK,
        next_required_frame=36,
    )
    runtime.commit_prevalidated_state_plan(planner.seal())

    runtime.update_frame(None, 18)
    replacement = runtime.begin_state_batch(18, "frozen-rate-refresh")
    refreshed = replacement.replace_frozen(
        type(frozen)(
            frozen.instance_ref,
            frozen.subject_ref,
            frozen.state_link_ref,
            frozen.created_frame,
            42,
            0.5,
            18,
        )
    )
    runtime.commit_prevalidated_state_plan(replacement.seal())

    assert frozen.decay_rate == 0.4
    assert frozen.decay_rate_updated_frame == 12
    assert refreshed.decay_rate == 0.5
    assert refreshed.decay_rate_updated_frame == 18


def test_creating_a_new_frozen_state_consumes_prior_recovery_history():
    runtime = create_default_reaction_bootstrap().create_runtime()
    recovery_plan = runtime.begin_state_batch(0, "recovery")
    recovery_plan.create_freeze_recovery(subject_ref=TARGET, decay_rate=0.6)
    runtime.commit_prevalidated_state_plan(recovery_plan.seal())

    frozen_plan = runtime.begin_state_batch(0, "refreeze")
    frozen = frozen_plan.create_frozen(subject_ref=TARGET, state_link_ref=LINK)
    runtime.commit_prevalidated_state_plan(frozen_plan.seal())

    assert runtime.frozen_state_for(TARGET) == frozen
    assert runtime.freeze_recovery_state_for(TARGET) is None
    assert runtime.state_records == (frozen,)


def test_frozen_aura_and_state_link_must_be_one_to_one_and_same_subject():
    aura_runtime = AuraRuntime()
    aura_runtime.apply(
        AuraApplicationRequest(
            "aura:hydro",
            "aura:hydro:application",
            "impact:hydro",
            0,
            0,
            SOURCE,
            TARGET,
            Element.HYDRO,
            AuraStrength.WEAK,
        )
    )
    reaction_runtime = create_default_reaction_bootstrap().create_runtime()
    state_planner = reaction_runtime.begin_state_batch(0, "frozen")
    state_planner.create_frozen(subject_ref=TARGET, state_link_ref=LINK)
    aura_planner = aura_runtime.begin_batch(0, "frozen")
    frozen = aura_planner.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen",
            "aura:frozen:application",
            "impact:frozen",
            0,
            1,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(2),
        )
    )
    receipt = FrozenStateLinkBatchCoordinator(aura_runtime, reaction_runtime).commit_prevalidated(
        aura_planner.seal(),
        state_planner.seal(),
    )

    validate_frozen_state_links(
        aura_runtime.snapshot().targets,
        reaction_runtime.state_snapshot(0).records,
    )
    assert frozen.after is not None
    assert frozen.after.current_amount == AuraAmount(2)
    assert receipt.aura_receipt.version == aura_runtime.version
    assert receipt.reaction_state_receipt.version == reaction_runtime.version

    remove_state = reaction_runtime.begin_state_batch(0, "remove")
    remove_state.remove_frozen(subject_ref=TARGET)
    reaction_runtime.commit_prevalidated_state_plan(remove_state.seal())

    with pytest.raises(ElementalStateLinkConflictError, match="悬空 Link"):
        validate_frozen_state_links(
            aura_runtime.snapshot().targets,
            reaction_runtime.state_snapshot(0).records,
        )


def test_frozen_aura_refresh_uses_larger_current_or_new_amount():
    runtime = AuraRuntime()

    first = runtime.begin_batch(0, "frozen:first")
    first.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:first",
            "application:frozen:first",
            "impact:frozen:first",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(4),
        )
    )
    runtime.commit_prevalidated(first.seal())

    lower = runtime.begin_batch(0, "frozen:lower")
    lower_result = lower.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:lower",
            "application:frozen:lower",
            "impact:frozen:lower",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(2),
        )
    )
    runtime.commit_prevalidated(lower.seal())

    higher = runtime.begin_batch(0, "frozen:higher")
    higher_result = higher.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:higher",
            "application:frozen:higher",
            "impact:frozen:higher",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(6),
        )
    )
    runtime.commit_prevalidated(higher.seal())

    assert lower_result.after is not None
    assert lower_result.after.current_amount == AuraAmount(4)
    assert higher_result.after is not None
    assert higher_result.after.current_amount == AuraAmount(6)


def test_frozen_aura_refresh_can_replace_raw_amount_with_decay_projection():
    runtime = AuraRuntime()
    initial = runtime.begin_batch(0, "frozen:initial")
    initial.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:initial",
            "application:frozen:initial",
            "impact:frozen:initial",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount(4),
        )
    )
    runtime.commit_prevalidated(initial.seal())

    refreshed = runtime.begin_batch(0, "frozen:projected")
    result = refreshed.apply_frozen(
        FrozenAuraApplicationRequest(
            "aura:frozen:projected",
            "application:frozen:projected",
            "impact:frozen:projected",
            0,
            0,
            SOURCE,
            TARGET,
            LINK,
            AuraAmount("71/20"),
            replace_existing_amount=True,
        )
    )
    runtime.commit_prevalidated(refreshed.seal())

    assert result.after is not None
    assert result.after.current_amount == AuraAmount("71/20")
