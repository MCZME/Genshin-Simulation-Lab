"""资产模型、仓库协议和资产错误。"""

from genshin_sim.assets.composite import CompositeAssetRepository
from genshin_sim.assets.errors import AssetError, AssetNotFoundError, AssetValidationError
from genshin_sim.assets.models import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    AssetDbInfo,
    AssetKeyParts,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
    WeaponAsset,
    WeaponLevelStats,
    split_asset_key,
    validate_asset_key,
)
from genshin_sim.assets.repository import (
    AssetHandlerBindingRepository,
    AssetRepository,
    HandlerBinding,
)

__all__ = [
    "ArtifactSetAsset",
    "ArtifactSetBonus",
    "AssetDbInfo",
    "AssetError",
    "AssetHandlerBindingRepository",
    "AssetKeyParts",
    "AssetNotFoundError",
    "AssetRepository",
    "AssetValidationError",
    "CharacterAsset",
    "CharacterLevelStats",
    "CompositeAssetRepository",
    "EffectPayload",
    "HandlerBinding",
    "TalentScalingEntry",
    "WeaponAsset",
    "WeaponLevelStats",
    "split_asset_key",
    "validate_asset_key",
]
