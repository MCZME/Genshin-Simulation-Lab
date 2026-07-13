from __future__ import annotations

import pytest

from genshin_sim.core.mechanics import (
    CreateMechanicInstanceCommand,
    MechanicInstanceNotFoundError,
    MechanicLifecycleState,
    MechanicRuntime,
    RefreshMechanicExpiryCommand,
    RemoveMechanicInstanceCommand,
)


def _create(
    runtime: MechanicRuntime,
    *,
    frame: int = 10,
    duration_frames: int = 60,
    owner_ref: str = "active_team:team:player",
    mechanic_key: str = "test.shield",
):
    return runtime.create_instance(
        CreateMechanicInstanceCommand(
            capability_key="shield",
            mechanic_key=mechanic_key,
            handler_key="test.shield.handler",
            owner_ref=owner_ref,
            frame=frame,
            duration_frames=duration_frames,
        )
    )


def test_mechanic_instance_uses_half_open_lifecycle_boundary():
    runtime = MechanicRuntime()
    instance = _create(runtime)

    assert instance.is_active_at(10)
    assert instance.is_active_at(69)
    assert not instance.is_active_at(70)
    assert runtime.instance_store.active_instances(frame=69) == (instance,)
    assert runtime.instance_store.active_instances(frame=70) == ()


def test_mechanic_runtime_expires_due_instances_in_stable_order():
    runtime = MechanicRuntime()
    second = _create(runtime, frame=2, duration_frames=2, mechanic_key="test.second")
    first = _create(runtime, frame=1, duration_frames=3, mechanic_key="test.first")
    received = []
    runtime.subscribe_removal(received.append)

    records = runtime.expire_due(4)

    assert [record.instance_id for record in records] == [
        second.instance_id,
        first.instance_id,
    ]
    assert [record.reason for record in records] == ["expired", "expired"]
    assert all(
        record.instance.lifecycle_state is MechanicLifecycleState.EXPIRED for record in records
    )
    assert received == list(records)
    assert runtime.instance_store.active_instances() == ()


def test_mechanic_store_indexes_by_owner_capability_and_mechanic_key():
    runtime = MechanicRuntime()
    first = _create(runtime, mechanic_key="test.alpha")
    _create(runtime, mechanic_key="test.beta")
    _create(runtime, owner_ref="character:slot_1", mechanic_key="test.alpha")

    assert runtime.instance_store.active_instances(
        frame=10,
        owner_ref="active_team:team:player",
        capability_key="shield",
        mechanic_key="test.alpha",
    ) == (first,)


def test_mechanic_runtime_explicit_removal_keeps_audit_record():
    runtime = MechanicRuntime()
    instance = _create(runtime)

    record = runtime.remove_instance(
        RemoveMechanicInstanceCommand(
            instance_id=instance.instance_id,
            frame=12,
            reason="dispelled",
        )
    )

    assert record.reason == "dispelled"
    assert record.instance.lifecycle_state is MechanicLifecycleState.REMOVED
    assert record.instance.removed_frame == 12
    assert runtime.instance_store.require(instance.instance_id) == record.instance
    with pytest.raises(MechanicInstanceNotFoundError):
        runtime.instance_store.require_active(instance.instance_id)


def test_mechanic_runtime_refreshes_only_at_an_active_frame():
    runtime = MechanicRuntime()
    instance = _create(runtime, frame=10, duration_frames=10)

    refreshed = runtime.refresh_expiry(
        RefreshMechanicExpiryCommand(
            instance_id=instance.instance_id,
            frame=15,
            expires_at_frame=30,
        )
    )

    assert refreshed.expires_at_frame == 30
    with pytest.raises(MechanicInstanceNotFoundError):
        runtime.refresh_expiry(
            RefreshMechanicExpiryCommand(
                instance_id=instance.instance_id,
                frame=30,
                expires_at_frame=40,
            )
        )


@pytest.mark.parametrize("frame", [5, 20, 25])
def test_mechanic_runtime_rejects_explicit_removal_outside_active_interval(frame):
    runtime = MechanicRuntime()
    instance = _create(runtime, frame=10, duration_frames=10)

    with pytest.raises(MechanicInstanceNotFoundError):
        runtime.remove_instance(
            RemoveMechanicInstanceCommand(
                instance_id=instance.instance_id,
                frame=frame,
                reason="dispelled",
            )
        )

    assert runtime.instance_store.require_active(instance.instance_id) == instance


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frame": -1},
        {"duration_frames": 0},
        {"duration_frames": True},
        {"owner_ref": ""},
    ],
)
def test_mechanic_create_command_rejects_invalid_inputs(kwargs):
    defaults = {
        "capability_key": "shield",
        "mechanic_key": "test.shield",
        "handler_key": "test.shield.handler",
        "owner_ref": "active_team:team:player",
        "frame": 0,
        "duration_frames": 1,
    }
    defaults.update(kwargs)

    with pytest.raises(ValueError):
        CreateMechanicInstanceCommand(**defaults)
