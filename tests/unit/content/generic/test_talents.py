from __future__ import annotations

from collections.abc import Sequence

import pytest

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.generic.talents import (
    ScalingCompileError,
    ScalingCompiler,
    TalentLevelResolver,
    TalentValidationError,
)


def _scaling_entry(
    *,
    entry_key: str = "character.test.normal_attack.line_01_param_1",
    values: Sequence[object] | None = None,
    mode: str = "level_table",
    level_min: int = 1,
    level_max: int = 15,
    schema_version: int = 1,
) -> TalentScalingEntry:
    return TalentScalingEntry(
        character_key="character:test",
        talent_key="normal_attack",
        entry_key=entry_key,
        label="测试倍率",
        scaling={
            "schema_version": schema_version,
            "mode": mode,
            "level_min": level_min,
            "level_max": level_max,
            "components": [
                {
                    "kind": "plain_ratio",
                    "source_param": "param1",
                    "values": values or [0.5 + index * 0.01 for index in range(15)],
                }
            ],
        },
    )


def test_talent_level_resolver_merges_boosts_and_clamps():
    resolution = TalentLevelResolver.resolve(
        {"normal_attack": 6, "elemental_skill": 1},
        {"normal_attack": 3},
    )

    assert resolution.levels == {"normal_attack": 9, "elemental_skill": 1}
    assert resolution.boosts_applied == {"normal_attack": 3}


def test_talent_level_resolver_clamps_to_max_level():
    resolution = TalentLevelResolver.resolve(
        {"normal_attack": 14},
        {"normal_attack": 3},
        max_level=15,
    )

    assert resolution.levels == {"normal_attack": 15}


def test_talent_level_resolver_rejects_boost_for_missing_talent():
    with pytest.raises(TalentValidationError, match="未配置"):
        TalentLevelResolver.resolve(
            {"normal_attack": 1},
            {"elemental_skill": 3},
        )


def test_talent_level_resolver_rejects_invalid_configured_level():
    with pytest.raises(TalentValidationError, match="1 到"):
        TalentLevelResolver.resolve({"normal_attack": 0})


def test_scaling_compiler_compiles_level_table():
    compiled = ScalingCompiler.compile_entry(_scaling_entry(), level=6)

    assert compiled.entry_key == "character.test.normal_attack.line_01_param_1"
    assert compiled.talent_key == "normal_attack"
    assert compiled.level == 6
    assert len(compiled.components) == 1
    component = compiled.components[0]
    assert component.component_key == ("character.test.normal_attack.line_01_param_1.param1")
    assert component.kind == "plain_ratio"
    assert component.value == pytest.approx(0.55)


def test_scaling_compiler_rejects_level_out_of_range():
    with pytest.raises(ScalingCompileError, match="1~15"):
        ScalingCompiler.compile_entry(_scaling_entry(), level=16)


def test_scaling_compiler_rejects_unsupported_mode():
    with pytest.raises(ScalingCompileError, match="level_table"):
        ScalingCompiler.compile_entry(_scaling_entry(mode="linear"), level=1)


def test_scaling_compiler_rejects_value_count_mismatch():
    entry = _scaling_entry(values=[0.5])

    with pytest.raises(ScalingCompileError, match="数量"):
        ScalingCompiler.compile_entry(entry, level=1)


def test_scaling_compiler_rejects_non_numeric_value():
    entry = _scaling_entry(
        values=[0.5, "x", *([0.5] * 13)],
    )

    with pytest.raises(ScalingCompileError, match="不是数字"):
        ScalingCompiler.compile_entry(entry, level=2)
