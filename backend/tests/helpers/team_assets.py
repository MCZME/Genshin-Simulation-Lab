"""队伍级资产测试纯构造器。

供单元与 golden 装配测试共享，避免各文件复制角色资产 bundle 构造。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from genshin_sim.assets.models import CharacterAsset, CharacterLevelStats


@dataclass(frozen=True, slots=True)
class TeamAssetBundle:
    """单个队伍槽位的角色资产数据包。"""

    slot: int
    character: CharacterAsset
    character_level_stats: CharacterLevelStats
    weapon: None = None
    weapon_level_stats: None = None
    artifact_sets: tuple[object, ...] = ()
    artifact_bonuses: tuple[object, ...] = ()
    effect_payloads: tuple[object, ...] = ()
    talent_scalings: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class TeamAttributeBundle:
    """属性运行时需要的槽位属性数据包。"""

    slot: int
    character_level_stats: CharacterLevelStats
    weapon_level_stats: None = None


def make_character_asset(
    slot: int,
    element: str,
    *,
    asset_key: str | None = None,
    name: str | None = None,
) -> CharacterAsset:
    """构造带稳定测试 handler_key 的角色资产。"""

    final_key = asset_key or f"character:{element}_{slot}"
    return CharacterAsset(
        asset_key=final_key,
        source_id=final_key.removeprefix("character:"),
        name=name or f"slot-{slot}",
        element=element,
        weapon_type="sword",
        rarity=4,
        burst_energy_cost=60.0,
        handler_key="generic.test_character",
    )


def make_character_stats(
    slot: int,
    *,
    level: int = 90,
    ascension_phase: int = 6,
    base_hp: float = 10000,
    base_atk: float = 1000,
    base_def: float = 700,
) -> CharacterLevelStats:
    """构造槽位对应的等级属性。"""

    return CharacterLevelStats(
        character_key=f"character:slot_{slot}",
        level=level,
        ascension_phase=ascension_phase,
        base_hp=base_hp,
        base_atk=base_atk,
        base_def=base_def,
    )


def make_team_asset_bundles(
    elements: Iterable[str],
    *,
    base_hp: float = 10000,
    base_atk: float = 1000,
    base_def: float = 700,
) -> tuple[TeamAssetBundle, ...]:
    """按元素序列构造 1..N 槽位的角色资产数据包。"""

    return tuple(
        TeamAssetBundle(
            slot=slot,
            character=make_character_asset(slot, element),
            character_level_stats=make_character_stats(
                slot,
                base_hp=base_hp,
                base_atk=base_atk,
                base_def=base_def,
            ),
        )
        for slot, element in enumerate(elements, start=1)
    )


def make_attribute_bundles(
    bundles: Iterable[TeamAssetBundle],
) -> tuple[TeamAttributeBundle, ...]:
    """从队伍资产数据包派生属性运行时输入。"""

    return tuple(
        TeamAttributeBundle(slot=bundle.slot, character_level_stats=bundle.character_level_stats)
        for bundle in bundles
    )
