from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from genshin_sim.assets import AssetValidationError
from genshin_sim.infrastructure.assets_project_amber._artifacts import (
    _build_artifact_set_bonuses,
)
from genshin_sim.infrastructure.assets_project_amber._characters import (
    _build_character_effect_payloads,
    _build_character_level_stats,
    _build_talent_scalings,
)
from genshin_sim.infrastructure.assets_project_amber._common import (
    _hash_cache_inputs,
    _payload_data,
    _read_json,
)
from genshin_sim.infrastructure.assets_project_amber._indexes import (
    _build_artifact_sets,
    _build_characters,
    _build_weapons,
)
from genshin_sim.infrastructure.assets_project_amber._weapons import (
    _build_weapon_effect_payloads,
    _build_weapon_level_stats,
)
from genshin_sim.infrastructure.assets_project_amber.fetcher import (
    PROJECT_AMBER_LANGUAGE,
    PROJECT_AMBER_SOURCE_NAME,
    PROJECT_AMBER_SOURCE_VERSION,
)
from genshin_sim.infrastructure.assets_sqlite.manifest import (
    HANDLER_OVERLAY_UPDATED_AT,
    AssetManifest,
    dump_asset_manifest,
)
from genshin_sim.infrastructure.assets_sqlite.manifest_baseline import (
    AssetManifestDiff,
    apply_manifest_baseline,
)
from genshin_sim.infrastructure.assets_sqlite.schema import ASSET_SCHEMA_VERSION

PROJECT_AMBER_MANIFEST_IMPORTER_VERSION = "project-amber-yatta-manifest-converter-1"


@dataclass(frozen=True, slots=True)
class ProjectAmberManifestBuildSummary:
    output_path: Path
    source_cache_dir: Path
    character_count: int
    character_level_stat_count: int
    weapon_count: int
    weapon_level_stat_count: int
    artifact_set_count: int
    artifact_set_bonus_count: int
    talent_scaling_count: int
    effect_payload_count: int
    content_hash: str
    diff: AssetManifestDiff
    degraded_affixes: tuple[str, ...] = ()


def build_asset_manifest_from_project_amber_cache(
    source_cache_dir: str | Path,
    output_path: str | Path,
) -> ProjectAmberManifestBuildSummary:
    """从 raw source cache 全量重建标准资产 manifest。

    manifest 每次全量重建，但 handler 覆盖是叠加在生成物上的本地状态：若
    ``output_path`` 上已有 manifest，则以其为基线继承 handler 绑定，并给出本次
    更新相对基线的差异（新增 / 消失 / 内容变化资产、继承与丢弃的绑定）。
    """

    cache_dir = Path(source_cache_dir)
    target_path = Path(output_path)

    cache_meta = _load_cache_meta(cache_dir)
    avatar_index = _payload_data(_read_json(cache_dir / "avatar" / "index.json"), "avatar/index")
    weapon_index = _payload_data(_read_json(cache_dir / "weapon" / "index.json"), "weapon/index")
    reliquary_index = _payload_data(
        _read_json(cache_dir / "reliquary" / "index.json"),
        "reliquary/index",
    )
    avatar_curve = _payload_data(
        _read_json(cache_dir / "static" / "avatarCurve.json"),
        "static/avatarCurve",
    )
    weapon_curve = _payload_data(
        _read_json(cache_dir / "static" / "weaponCurve.json"),
        "static/weaponCurve",
    )

    characters = _build_characters(cache_dir, avatar_index)
    character_level_stats = _build_character_level_stats(cache_dir, characters, avatar_curve)
    talent_scalings = _build_talent_scalings(cache_dir, characters)
    weapons = _build_weapons(weapon_index)
    weapon_level_stats = _build_weapon_level_stats(cache_dir, weapons, weapon_curve)
    degraded_affixes: list[str] = []
    effect_payloads = (
        *_build_character_effect_payloads(cache_dir, characters),
        *_build_weapon_effect_payloads(
            cache_dir,
            weapons,
            degraded_affixes=degraded_affixes,
        ),
    )
    artifact_sets = _build_artifact_sets(reliquary_index)
    artifact_set_bonuses = _build_artifact_set_bonuses(reliquary_index, artifact_sets)
    content_hash = str(cache_meta.get("content_hash") or _hash_cache_inputs(cache_dir))

    rows = AssetManifest(
        meta=_build_asset_meta(cache_meta, content_hash),
        characters=characters,
        character_level_stats=character_level_stats,
        weapons=weapons,
        weapon_level_stats=weapon_level_stats,
        artifact_sets=artifact_sets,
        artifact_set_bonuses=artifact_set_bonuses,
        talent_scalings=talent_scalings,
        effect_payloads=effect_payloads,
    )
    merged, diff = apply_manifest_baseline(target_path, rows)
    if diff.baseline_handler_overlay_updated_at is not None:
        merged = replace(
            merged,
            meta={
                **merged.meta,
                HANDLER_OVERLAY_UPDATED_AT: diff.baseline_handler_overlay_updated_at,
            },
        )
    dump_asset_manifest(merged, target_path)

    return ProjectAmberManifestBuildSummary(
        output_path=target_path,
        source_cache_dir=cache_dir,
        character_count=len(characters),
        character_level_stat_count=len(character_level_stats),
        weapon_count=len(weapons),
        weapon_level_stat_count=len(weapon_level_stats),
        artifact_set_count=len(artifact_sets),
        artifact_set_bonus_count=len(artifact_set_bonuses),
        talent_scaling_count=len(talent_scalings),
        effect_payload_count=len(effect_payloads),
        content_hash=content_hash,
        diff=diff,
        degraded_affixes=tuple(degraded_affixes),
    )


def _load_cache_meta(cache_dir: Path) -> Mapping[str, Any]:
    manifest_path = cache_dir / "fetch_manifest.json"
    if not manifest_path.exists():
        return {}
    payload = _read_json(manifest_path)
    if payload.get("kind") != "project_amber_source_cache":
        raise AssetValidationError("fetch_manifest.json 不是 Project Amber raw cache manifest")
    return payload


def _build_asset_meta(cache_meta: Mapping[str, Any], content_hash: str) -> dict[str, str]:
    source_name = str(cache_meta.get("source_name") or PROJECT_AMBER_SOURCE_NAME)
    source_version = str(cache_meta.get("source_version") or PROJECT_AMBER_SOURCE_VERSION)
    language = str(cache_meta.get("language") or PROJECT_AMBER_LANGUAGE)
    fetched_at = cache_meta.get("fetched_at")
    data_version = f"{source_name}:{source_version}:{content_hash[:12]}"

    rows = {
        "schema_version": ASSET_SCHEMA_VERSION,
        "data_version": data_version,
        "importer_version": PROJECT_AMBER_MANIFEST_IMPORTER_VERSION,
        "source_name": source_name,
        "source_version": source_version,
        "source_language": language,
        "content_hash": content_hash,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if fetched_at is not None:
        rows["source_fetched_at"] = str(fetched_at)
    return rows
