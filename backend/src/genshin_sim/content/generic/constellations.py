"""generic 命座框架：静态解锁解析与效果挂载。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from genshin_sim.content.definitions.content_unit import ContentUnit
from genshin_sim.content.definitions.effects import (
    ConstellationDefinition,
    EffectSpec,
    UnlockValues,
)


class ConstellationMountError(Exception):
    """命座解析或挂载错误基类。"""


class DuplicateEffectKeyError(ConstellationMountError, ValueError):
    """挂载时与既有效果键冲突。"""


def resolve_unlocked_constellations(
    definitions: Sequence[ConstellationDefinition],
    values: UnlockValues,
) -> tuple[ConstellationDefinition, ...]:
    """按命座序号与键稳定排序，返回解锁生效的命座定义。"""

    unlocked = tuple(definition for definition in definitions if definition.unlock.evaluate(values))
    return tuple(sorted(unlocked, key=lambda item: (item.unlock.threshold, item.key)))


def resolve_effect_specs(
    definitions: Sequence[ConstellationDefinition],
    values: UnlockValues,
) -> tuple[EffectSpec, ...]:
    """返回解锁生效命座的效果规格。"""

    return tuple(
        definition.as_effect_spec()
        for definition in resolve_unlocked_constellations(definitions, values)
    )


def mount_effects(
    unit: ContentUnit,
    effects: Sequence[EffectSpec],
) -> ContentUnit:
    """把生效效果并入内容单元；effect_key 冲突在编译期失败。"""

    existing_keys = {effect.effect_key for effect in unit.effects}
    duplicates = [effect.effect_key for effect in effects if effect.effect_key in existing_keys]
    if duplicates:
        keys = ", ".join(duplicates)
        raise DuplicateEffectKeyError(f"挂载效果与既有 effect_key 冲突：{keys}")
    return replace(unit, effects=(*unit.effects, *tuple(effects)))
