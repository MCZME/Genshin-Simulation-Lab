"""generic 天赋框架：有效天赋等级解析与倍率编译。

运行期不查询倍率表；配置等级经参数改写（命座等级提升）得到有效等级后，
在内容编译期把资产倍率表编译为确定值。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError


class TalentFrameworkError(Exception):
    """天赋框架错误基类。"""


class TalentValidationError(TalentFrameworkError, ValueError):
    """天赋等级或倍率数据不合法。"""


class ScalingCompileError(TalentFrameworkError, ValueError):
    """倍率编译失败。"""


def index_talent_scalings(
    character_key: str,
    talent_scalings: tuple[TalentScalingEntry, ...],
) -> dict[tuple[str, str, str], TalentScalingEntry]:
    """索引（角色, 天赋, 具体文本）资产倍率条目。

    归属不符或文本重复都在内容编译期确定性报错；具体文本在该三元组内唯一。
    """

    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry] = {}
    for entry in talent_scalings:
        if entry.character_key != character_key:
            raise ContentUnitValidationError(
                f"角色倍率条目归属不符：{entry.entry_key}（{character_key}）"
            )
        key = (entry.character_key, entry.talent_key, entry.label)
        if key in entries_by_key:
            raise ContentUnitValidationError(
                f"角色倍率条目标签重复：{entry.label}（{character_key}）"
            )
        entries_by_key[key] = entry
    return entries_by_key


@dataclass(frozen=True, slots=True)
class TalentLevelResolution:
    """参数改写后的有效天赋等级。"""

    levels: Mapping[str, int] = field(default_factory=dict)
    boosts_applied: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "levels", dict(self.levels))
        object.__setattr__(self, "boosts_applied", dict(self.boosts_applied))


class TalentLevelResolver:
    """把配置天赋等级与编译期等级提升合并为有效等级。"""

    @staticmethod
    def resolve(
        talent_levels: Mapping[str, int],
        boosts: Mapping[str, int] | None = None,
        *,
        max_level: int = 15,
    ) -> TalentLevelResolution:
        if isinstance(max_level, bool) or not isinstance(max_level, int) or max_level < 1:
            raise TalentValidationError("max_level 必须是正整数")
        levels = {
            _validate_talent_key(key): _validate_talent_level(level, max_level)
            for key, level in talent_levels.items()
        }
        boost_values = {
            _validate_talent_key(key): _validate_boost(level)
            for key, level in (boosts or {}).items()
        }
        missing = set(boost_values) - set(levels)
        if missing:
            keys = ", ".join(sorted(missing))
            raise TalentValidationError(f"等级提升作用于未配置的天赋：{keys}")

        merged: dict[str, int] = {}
        applied: dict[str, int] = {}
        for key, level in levels.items():
            boost = boost_values.get(key, 0)
            merged[key] = min(level + boost, max_level)
            if boost:
                applied[key] = boost
        return TalentLevelResolution(levels=merged, boosts_applied=applied)


@dataclass(frozen=True, slots=True)
class CompiledScalingComponent:
    """单个倍率项的编译结果。"""

    component_key: str
    kind: str
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.component_key, str) or not self.component_key.strip():
            raise ScalingCompileError("component_key 必须是非空字符串")
        if self.kind not in {"plain_ratio", "plain_value"}:
            raise ScalingCompileError(f"不支持的倍率组件 kind：{self.kind}")
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise ScalingCompileError("倍率值必须是数字")
        object.__setattr__(self, "value", float(self.value))


@dataclass(frozen=True, slots=True)
class CompiledScaling:
    """一个天赋条目在指定等级下的编译后倍率项集合。"""

    entry_key: str
    talent_key: str
    level: int
    components: Sequence[CompiledScalingComponent] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.entry_key, str) or not self.entry_key.strip():
            raise ScalingCompileError("entry_key 必须是非空字符串")
        if not isinstance(self.talent_key, str) or not self.talent_key.strip():
            raise ScalingCompileError("talent_key 必须是非空字符串")
        _validate_talent_level(self.level, 15)
        object.__setattr__(self, "components", tuple(self.components))


class ScalingCompiler:
    """把资产倍率表条目编译为指定等级的确定倍率项。"""

    @staticmethod
    def compile_entry(
        entry: TalentScalingEntry,
        level: int,
    ) -> CompiledScaling:
        if not isinstance(entry, TalentScalingEntry):
            raise TypeError("entry 必须是 TalentScalingEntry")
        scaling = entry.scaling
        if not isinstance(scaling, Mapping):
            raise ScalingCompileError(f"{entry.entry_key} 的 scaling 必须是对象")
        if scaling.get("schema_version") != 1:
            raise ScalingCompileError(f"{entry.entry_key} 只支持 schema_version=1 的倍率表")
        if scaling.get("mode") != "level_table":
            raise ScalingCompileError(f"{entry.entry_key} 只支持 level_table 倍率模式")

        level_min = _require_int(scaling, "level_min", entry)
        level_max = _require_int(scaling, "level_max", entry)
        if level_min < 1 or level_max < level_min:
            raise ScalingCompileError(f"{entry.entry_key} 的倍率等级区间不合法")
        if (
            isinstance(level, bool)
            or not isinstance(level, int)
            or not level_min <= level <= level_max
        ):
            raise ScalingCompileError(
                f"{entry.entry_key} 需要 {level_min}~{level_max} 级，实际 {level}"
            )

        raw_components = scaling.get("components")
        if not isinstance(raw_components, Sequence) or isinstance(
            raw_components,
            (str, bytes, bytearray),
        ):
            raise ScalingCompileError(f"{entry.entry_key} 的 components 必须是数组")
        compiled: list[CompiledScalingComponent] = []
        expected_count = level_max - level_min + 1
        for index, raw in enumerate(raw_components):
            if not isinstance(raw, Mapping):
                raise ScalingCompileError(f"{entry.entry_key} 的 components[{index}] 必须是对象")
            source_param = raw.get("source_param")
            if not isinstance(source_param, str) or not source_param.strip():
                raise ScalingCompileError(
                    f"{entry.entry_key} 的 components[{index}] 缺少 source_param"
                )
            kind = raw.get("kind")
            if kind not in {"plain_ratio", "plain_value"}:
                raise ScalingCompileError(
                    f"{entry.entry_key} 的 components[{index}] kind 不受支持：{kind}"
                )
            values = raw.get("values")
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
                raise ScalingCompileError(
                    f"{entry.entry_key} 的 components[{index}] values 必须是数组"
                )
            if len(values) != expected_count:
                raise ScalingCompileError(
                    f"{entry.entry_key} 的 components[{index}] 等级值数量与区间不符"
                )
            value = values[level - level_min]
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ScalingCompileError(
                    f"{entry.entry_key} 的 components[{index}] 等级 {level} 值不是数字"
                )
            compiled.append(
                CompiledScalingComponent(
                    component_key=f"{entry.entry_key}.{source_param}",
                    kind=kind,
                    value=float(value),
                )
            )
        if not compiled:
            raise ScalingCompileError(f"{entry.entry_key} 没有可编译的倍率组件")
        return CompiledScaling(
            entry_key=entry.entry_key,
            talent_key=entry.talent_key,
            level=level,
            components=tuple(compiled),
        )


def _validate_talent_key(key: str) -> str:
    if not isinstance(key, str) or not key.strip():
        raise TalentValidationError("天赋键必须是非空字符串")
    return key


def _validate_talent_level(level: int, max_level: int) -> int:
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= max_level:
        raise TalentValidationError(f"天赋等级必须在 1 到 {max_level} 之间")
    return level


def _validate_boost(boost: int) -> int:
    if isinstance(boost, bool) or not isinstance(boost, int) or boost < 0:
        raise TalentValidationError("天赋等级提升必须是非负整数")
    return boost


def _require_int(scaling: Mapping[str, Any], key: str, entry: TalentScalingEntry) -> int:
    value = scaling.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScalingCompileError(f"{entry.entry_key} 的 {key} 必须是整数")
    return value
