from __future__ import annotations

import pytest

from genshin_sim.content.generic.timed_action import (
    TimedActionSpec,
    TimedActionSpecValidationError,
    build_timed_actions,
)
from genshin_sim.core.actions import TargetingSpec


def test_timed_action_spec_validates_impact_and_hit_frame_relationship():
    with pytest.raises(TimedActionSpecValidationError, match="hit_frame"):
        TimedActionSpec(
            action_key="a",
            duration_frames=10,
            impact_key="a.hit",
        )
    with pytest.raises(TimedActionSpecValidationError, match="impact_key"):
        TimedActionSpec(
            action_key="a",
            duration_frames=10,
            hit_frame=5,
        )
    TimedActionSpec(
        action_key="jump",
        duration_frames=31,
        hit_frame=31,
        impact_key="jump.hit",
    )
    TimedActionSpec(
        action_key="elemental_skill",
        duration_frames=5,
        hit_frame=42,
        impact_key="elemental_skill.hit",
    )


def test_build_timed_actions_maps_specs_to_timed_actions():
    actions = build_timed_actions(
        (
            TimedActionSpec(
                action_key="character.test.normal_attack.1",
                duration_frames=15,
                hit_frame=6,
                impact_key="character.test.normal_attack.1.hit",
                transitions={"normal_attack": 15},
            ),
            TimedActionSpec(
                action_key="character.test.normal_attack.2",
                duration_frames=20,
                hit_frame=8,
                impact_key="character.test.normal_attack.2.hit",
                transitions={"normal_attack": 20},
            ),
        )
    )

    assert [action.action_key for action in actions] == [
        "character.test.normal_attack.1",
        "character.test.normal_attack.2",
    ]
    first = actions[0]
    assert first.duration_frames == 15
    assert first.impact_keys == ("character.test.normal_attack.1.hit",)
    assert first.impact_frame_offsets == {"character.test.normal_attack.1.hit": 6}
    assert actions[1].impact_keys == ("character.test.normal_attack.2.hit",)


def test_build_timed_actions_passes_targeting_through():
    actions = build_timed_actions(
        (
            TimedActionSpec(
                action_key="character.test.normal_attack.1",
                duration_frames=15,
                hit_frame=6,
                impact_key="character.test.normal_attack.1.hit",
                targeting=TargetingSpec(radius=1.0),
            ),
        )
    )

    assert actions[0].targeting is not None
    assert actions[0].targeting.radius == 1.0

