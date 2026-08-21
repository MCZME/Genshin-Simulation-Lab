"""芭芭拉内容单元注册与倍率条目校验。"""

from __future__ import annotations

import pytest

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_HIT_IMPACT_KEYS,
    BARBARA_RING_OBJECT_KEY,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.generic.chain_state import (
    CHAIN_STATE_LAST_ACTION_KEY,
    CHAIN_STATE_LAST_START_FRAME,
)
from genshin_sim.core.elements import AuraAmount
from tests.helpers.barbara_assets import barbara_scaling_entries


def test_barbara_content_unit_registers_actions_ring_cooldown_and_icd(
    barbara_content_unit,
):
    unit = barbara_content_unit(talent_levels={"normal_attack": 1, "elemental_skill": 1})

    assert unit.handler_key == BARBARA_CHARACTER_HANDLER_KEY
    assert unit.action_interpreter is not None
    assert len(unit.actions) == 9
    assert unit.state_schema is not None
    assert unit.state_schema.owner_ref == "character:slot_1"
    assert unit.state_schema.defaults() == {
        CHAIN_STATE_LAST_ACTION_KEY: "",
        CHAIN_STATE_LAST_START_FRAME: 0,
    }
    assert tuple(unit.impact_factories) == BARBARA_HIT_IMPACT_KEYS
    assert tuple(unit.created_object_behaviors) == (
        f"{BARBARA_RING_OBJECT_KEY}.heal",
        f"{BARBARA_RING_OBJECT_KEY}.wet",
    )
    assert len(unit.cooldown_definitions) == 2
    cooldown = unit.cooldown_definitions[0]
    assert cooldown.key.ability_key == "elemental_skill"
    assert cooldown.key.subject.subject_id == "character:slot_1"
    assert cooldown.base_duration_frames == 1920
    burst_cooldown = unit.cooldown_definitions[1]
    assert burst_cooldown.key.ability_key == "elemental_burst"
    assert burst_cooldown.base_duration_frames == 1200
    ring_icd = unit.aura_icd_definitions[0]
    assert ring_icd.sequence_key == "芭芭拉水环"
    assert ring_icd.reset_interval_frames == 150
    assert ring_icd.application_sequence == tuple(
        AuraAmount(value)
        for value in (
            1,
            0,
            0,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
    )


@pytest.mark.parametrize(
    ("case", "message"),
    (
        pytest.param("duplicate_label", "标签重复", id="duplicate_label"),
        pytest.param("missing_burst", "元素爆发缺少资产倍率条目", id="missing_burst"),
    ),
)
def test_barbara_content_unit_rejects_malformed_scaling_entries(
    barbara_content_unit,
    case: str,
    message: str,
):
    entries = barbara_scaling_entries()
    if case == "duplicate_label":
        entries = (
            *entries,
            TalentScalingEntry(
                character_key="character:10000014",
                talent_key="normal_attack",
                entry_key="line_09_duplicate",
                label="一段伤害",
                scaling=entries[0].scaling,
                tags=("normal_attack", "ratio"),
            ),
        )
    else:
        entries = tuple(entry for entry in entries if entry.talent_key != "elemental_burst")

    with pytest.raises(ContentUnitValidationError, match=message):
        barbara_content_unit(talent_scalings=entries)
