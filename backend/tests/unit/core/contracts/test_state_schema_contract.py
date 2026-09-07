from __future__ import annotations

import pytest

from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
    StateSchemaConflictError,
    StateSchemaFragment,
    StateSchemaValidationError,
    merge_state_schema_fragments,
)


def test_state_field_requires_typed_default():
    with pytest.raises(StateSchemaValidationError, match="默认值"):
        StateField(name="stacks", field_type=StateFieldType.INT, default="x")


def test_enum_field_requires_allowed_values():
    with pytest.raises(StateSchemaValidationError, match="allowed_values"):
        StateField(
            name="mode",
            field_type=StateFieldType.ENUM,
            default="a",
            allowed_values=(),
        )


def test_enum_field_rejects_default_outside_allowed_values():
    with pytest.raises(StateSchemaValidationError, match="默认值"):
        StateField(
            name="mode",
            field_type=StateFieldType.ENUM,
            default="b",
            allowed_values=("a",),
        )


def test_numeric_constraints_validate_defaults():
    with pytest.raises(StateSchemaValidationError, match="负数"):
        StateField(
            name="stacks",
            field_type=StateFieldType.INT,
            default=-1,
            non_negative=True,
        )
    with pytest.raises(StateSchemaValidationError, match="max_value"):
        StateField(
            name="stacks",
            field_type=StateFieldType.INT,
            default=4,
            max_value=3,
        )


def test_state_field_validates_written_values():
    field = StateField(
        name="stacks",
        field_type=StateFieldType.INT,
        default=0,
        non_negative=True,
        max_value=3,
    )

    field.validate_value(2)
    with pytest.raises(StateSchemaValidationError, match="不能超过"):
        field.validate_value(4)
    with pytest.raises(StateSchemaValidationError, match="不能为负数"):
        field.validate_value(-1)
    with pytest.raises(StateSchemaValidationError, match="期望 int"):
        field.validate_value(True)


def test_clamp_requires_explicit_opt_in():
    field = StateField(name="stacks", field_type=StateFieldType.INT, default=0)

    with pytest.raises(StateSchemaValidationError, match="clamp"):
        field.clamp_value(5)

    clamped = StateField(
        name="stacks",
        field_type=StateFieldType.INT,
        default=0,
        max_value=3,
        clamp=True,
    )
    assert clamped.clamp_value(5) == 3


def test_schema_defaults_and_patch_lookup():
    schema = StateSchema(
        owner_ref="character:slot:1",
        fields=(
            StateField(name="stacks", field_type=StateFieldType.INT, default=0),
            StateField(name="active", field_type=StateFieldType.BOOL, default=False),
        ),
    )

    assert schema.defaults() == {"stacks": 0, "active": False}
    schema.validate_patch("stacks", 2)
    with pytest.raises(StateSchemaValidationError, match="未知状态字段"):
        schema.validate_patch("missing", 1)


def test_fragment_requires_owner_ref():
    with pytest.raises(StateSchemaValidationError, match="owner_ref"):
        StateSchemaFragment(owner_ref="")


def test_fragment_rejects_duplicate_field_names():
    with pytest.raises(StateSchemaValidationError, match="字段名不能重复"):
        StateSchemaFragment(
            owner_ref="character:slot:1",
            fields=(
                StateField(name="stacks", field_type=StateFieldType.INT, default=0),
                StateField(name="stacks", field_type=StateFieldType.INT, default=0),
            ),
        )


def test_merge_combines_unique_fields_sorted():
    merged = merge_state_schema_fragments(
        "character:slot_1",
        (
            StateSchemaFragment(
                owner_ref="character:slot_1",
                fields=(StateField(name="stacks", field_type=StateFieldType.INT, default=0),),
            ),
            StateSchemaFragment(
                owner_ref="character:slot_1",
                fields=(StateField(name="active", field_type=StateFieldType.BOOL, default=False),),
            ),
        ),
    )

    assert [item.name for item in merged.fields] == ["active", "stacks"]


def test_merge_duplicate_name_requires_explicit_share():
    fragment = StateSchemaFragment(
        owner_ref="character:slot_1",
        fields=(StateField(name="stacks", field_type=StateFieldType.INT, default=0),),
    )

    with pytest.raises(StateSchemaConflictError, match="未显式共享"):
        merge_state_schema_fragments("character:slot_1", (fragment, fragment))


def test_merge_shared_identical_fields_is_allowed():
    def make_fragment():
        return StateSchemaFragment(
            owner_ref="character:slot_1",
            fields=(
                StateField(
                    name="stacks",
                    field_type=StateFieldType.INT,
                    default=0,
                    shared=True,
                ),
            ),
        )

    merged = merge_state_schema_fragments(
        "character:slot_1",
        (make_fragment(), make_fragment()),
    )
    assert merged.field("stacks") is not None


def test_merge_shared_mismatched_shapes_fails():
    first = StateSchemaFragment(
        owner_ref="character:slot_1",
        fields=(
            StateField(
                name="stacks",
                field_type=StateFieldType.INT,
                default=0,
                shared=True,
            ),
        ),
    )
    second = StateSchemaFragment(
        owner_ref="character:slot_1",
        fields=(
            StateField(
                name="stacks",
                field_type=StateFieldType.FLOAT,
                default=0.0,
                shared=True,
            ),
        ),
    )

    with pytest.raises(StateSchemaConflictError, match="声明不一致"):
        merge_state_schema_fragments("character:slot_1", (first, second))


def test_merge_rejects_owner_mismatch():
    fragment = StateSchemaFragment(
        owner_ref="character:slot_2",
        fields=(StateField(name="stacks", field_type=StateFieldType.INT, default=0),),
    )

    with pytest.raises(StateSchemaConflictError, match="归属不一致"):
        merge_state_schema_fragments("character:slot_1", (fragment,))
