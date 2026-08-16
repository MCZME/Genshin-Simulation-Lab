from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from genshin_sim.assets import ArtifactSetAsset, ArtifactSetBonus, AssetValidationError
from genshin_sim.infrastructure.assets_project_amber._common import (
    _items_mapping,
    _numeric_sort_key,
    _require_mapping,
    _text_number_components,
)

_ARTIFACT_SET_BONUS_HANDLER_KEY = "artifact.unimplemented_set_bonus"


def _build_artifact_set_bonuses(
    reliquary_index_data: Mapping[str, Any],
    artifact_sets: tuple[ArtifactSetAsset, ...],
) -> tuple[ArtifactSetBonus, ...]:
    items = _items_mapping(reliquary_index_data, "reliquary/index")
    rows: list[ArtifactSetBonus] = []
    for artifact_set in artifact_sets:
        item = _require_mapping(
            items.get(artifact_set.source_id),
            f"reliquary.items[{artifact_set.source_id}]",
        )
        affixes = _require_mapping(
            item.get("affixList"),
            f"reliquary.items[{artifact_set.source_id}].affixList",
        )
        ordered_affixes = tuple(
            sorted(
                ((str(affix_id), raw_text) for affix_id, raw_text in affixes.items()),
                key=lambda affix: _numeric_sort_key(affix[0]),
            )
        )
        for index, (affix_id, raw_text) in enumerate(ordered_affixes):
            if not isinstance(raw_text, str) or not raw_text:
                raise AssetValidationError(
                    "reliquary.items"
                    f"[{artifact_set.source_id}].affixList[{affix_id}] 必须是非空字符串"
                )
            piece_count = _artifact_piece_count(index, len(ordered_affixes))
            rows.append(
                ArtifactSetBonus(
                    artifact_set_key=artifact_set.asset_key,
                    piece_count=piece_count,
                    handler_key=_ARTIFACT_SET_BONUS_HANDLER_KEY,
                    params=_artifact_set_bonus_params(
                        affix_id=affix_id,
                        piece_count=piece_count,
                        description=raw_text,
                    ),
                )
            )
    return tuple(rows)


def _artifact_piece_count(index: int, affix_count: int) -> int:
    if affix_count == 1:
        return 1
    if index == 0:
        return 2
    if index == 1:
        return 4
    raise AssetValidationError("圣遗物套装效果数量超过当前转换器支持范围")


def _artifact_set_bonus_params(
    *,
    affix_id: str,
    piece_count: int,
    description: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "project-amber-yatta",
        "source_affix_id": affix_id,
        "piece_count": piece_count,
        "source_template": description,
        "components": _text_number_components(description),
    }
