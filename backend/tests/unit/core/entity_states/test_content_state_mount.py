from __future__ import annotations

import pytest

from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)
from genshin_sim.core.entity_states.content_state import (
    ContentStateMount,
    ContentStateMountError,
)


def _schema(owner_ref: str = "character:slot_1") -> StateSchema:
    return StateSchema(
        owner_ref=owner_ref,
        fields=(
            StateField(
                name="stacks",
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
                max_value=3,
            ),
            StateField(
                name="hp_ratio",
                field_type=StateFieldType.FLOAT,
                default=1.0,
                non_negative=True,
                max_value=1.0,
                clamp=True,
            ),
        ),
    )


def test_mount_initializes_defaults_and_exposes_read_only_view():
    mount = ContentStateMount(state_key="character.test", schema=_schema())

    assert mount.state_key == "character.test"
    assert mount.owner == "character:slot_1"
    assert mount.get("stacks") == 0
    assert mount.values == {"stacks": 0, "hp_ratio": 1.0}


def test_mount_requires_owner_matching_schema_owner_ref():
    with pytest.raises(ContentStateMountError, match="一致"):
        ContentStateMount(
            state_key="character.test",
            schema=_schema(),
            owner="character:slot_2",
        )


def test_mount_applies_validated_patch_and_rejects_partial_write():
    mount = ContentStateMount(state_key="character.test", schema=_schema())

    mount.apply_patch({"stacks": 3})
    with pytest.raises(ContentStateMountError, match="不能超过"):
        mount.apply_patch({"stacks": 5, "hp_ratio": 0.5})

    assert mount.get("stacks") == 3
    assert mount.get("hp_ratio") == 1.0


def test_mount_clamps_fields_declared_with_clamp():
    mount = ContentStateMount(state_key="character.test", schema=_schema())

    mount.apply_patch({"hp_ratio": 1.5})

    assert mount.get("hp_ratio") == 1.0


def test_mount_snapshot_is_json_compatible():
    mount = ContentStateMount(
        state_key="character.test",
        schema=_schema(),
        initial_values={"stacks": 2},
    )

    assert mount.snapshot(frame=5) == {
        "owner_ref": "character:slot_1",
        "state_key": "character.test",
        "schema_version": 1,
        "frame": 5,
        "payload": {"stacks": 2, "hp_ratio": 1.0},
    }
