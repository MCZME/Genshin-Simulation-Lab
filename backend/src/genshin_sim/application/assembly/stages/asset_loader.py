"""数据查询阶段：规范化配置 -> 类型化资产数据包。"""

from __future__ import annotations

from genshin_sim.application.assembly.errors import MissingRuntimeAssetError
from genshin_sim.application.assembly.models import RuntimeAssetBundle
from genshin_sim.application.input import SimulationInput, TeamSlotConfig
from genshin_sim.assets import AssetError, AssetRepository
from genshin_sim.assets.models import ArtifactSetAsset, ArtifactSetBonus, TalentScalingEntry


class AssetBundleLoader:
    """按配置引用读取资产并做完整性校验。"""

    def __init__(self, asset_repository: AssetRepository) -> None:
        self.asset_repository = asset_repository

    def load(self, config: SimulationInput) -> tuple[RuntimeAssetBundle, ...]:
        return tuple(self._load_slot_assets(slot) for slot in config.team)

    def _load_slot_assets(self, slot: TeamSlotConfig) -> RuntimeAssetBundle:
        try:
            character = self.asset_repository.get_character(slot.character.asset_key)
            character_level_stats = self.asset_repository.get_character_level_stats(
                character.asset_key,
                slot.character.level,
            )

            weapon = None
            weapon_level_stats = None
            if slot.weapon is not None:
                weapon = self.asset_repository.get_weapon(slot.weapon.asset_key)
                weapon_level_stats = self.asset_repository.get_weapon_level_stats(
                    weapon.asset_key,
                    slot.weapon.level,
                )

            artifact_sets: list[ArtifactSetAsset] = []
            artifact_bonuses: list[ArtifactSetBonus] = []
            for artifact_set in slot.artifacts.sets:
                asset = self.asset_repository.get_artifact_set(artifact_set.asset_key)
                artifact_sets.append(asset)
                artifact_bonuses.extend(
                    sorted(
                        (
                            bonus
                            for bonus in self.asset_repository.get_artifact_set_bonuses(
                                artifact_set.asset_key
                            )
                            if bonus.piece_count <= artifact_set.pieces
                        ),
                        key=lambda bonus: bonus.piece_count,
                    )
                )

            effect_payloads = list(self.asset_repository.get_effect_payloads(character.asset_key))
            if weapon is not None:
                effect_payloads.extend(self.asset_repository.get_effect_payloads(weapon.asset_key))
            for artifact_set in artifact_sets:
                effect_payloads.extend(
                    self.asset_repository.get_effect_payloads(artifact_set.asset_key)
                )

            talent_scalings: list[TalentScalingEntry] = []
            for talent_key in slot.character.talents:
                talent_scalings.extend(
                    self.asset_repository.get_talent_scalings(character.asset_key, talent_key)
                )
        except (AssetError, LookupError) as exc:
            raise MissingRuntimeAssetError(f"加载队伍槽位 {slot.slot} 的资产失败：{exc}") from exc

        return RuntimeAssetBundle(
            slot=slot.slot,
            character=character,
            character_level_stats=character_level_stats,
            weapon=weapon,
            weapon_level_stats=weapon_level_stats,
            artifact_sets=tuple(artifact_sets),
            artifact_bonuses=tuple(artifact_bonuses),
            effect_payloads=tuple(effect_payloads),
            talent_scalings=tuple(talent_scalings),
        )
