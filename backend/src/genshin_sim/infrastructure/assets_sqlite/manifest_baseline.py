"""已有资产 manifest 作为基线的 handler 覆盖继承与差异计算。

标准资产 manifest 由转换器全量重建，而 handler 覆盖是叠加在生成物之上的本地状态。
重建时若不继承，已接入的 handler 绑定会静默退化为默认值（索引行回到 ``NULL``、
效果回到 ``*.unimplemented_*`` 占位键）。本模块读取目标路径上已有的 manifest，
把覆盖按稳定键继承到新构建的资产行上，并给出可读的变更差异。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from genshin_sim.assets import AssetValidationError
from genshin_sim.infrastructure.assets_sqlite.manifest import (
    HANDLER_OVERLAY_UPDATED_AT,
    AssetManifest,
    load_asset_manifest,
)

_PLACEHOLDER_MARKER = ".unimplemented"
_NON_NUMERIC_SORT_KEY = 10**12


@dataclass(frozen=True, slots=True)
class AssetGroupChanges:
    """单个资产类别的变更集合，键为资产身份。"""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.added) + len(self.removed) + len(self.changed)


@dataclass(frozen=True, slots=True)
class AssetManifestDiff:
    """新构建 manifest 相对基线的差异与 handler 继承结果。"""

    baseline_path: Path | None = None
    baseline_available: bool = False
    baseline_error: str | None = None
    baseline_handler_overlay_updated_at: str | None = None
    characters: AssetGroupChanges = field(default_factory=AssetGroupChanges)
    weapons: AssetGroupChanges = field(default_factory=AssetGroupChanges)
    artifact_sets: AssetGroupChanges = field(default_factory=AssetGroupChanges)
    carried_bindings: tuple[str, ...] = ()
    dropped_bindings: tuple[str, ...] = ()
    binding_conflicts: tuple[str, ...] = ()

    @property
    def has_asset_changes(self) -> bool:
        return bool(self.characters.total or self.weapons.total or self.artifact_sets.total)


def apply_manifest_baseline(
    baseline_path: str | Path,
    rows: AssetManifest,
) -> tuple[AssetManifest, AssetManifestDiff]:
    """把已有 manifest 的 handler 覆盖继承到新资产行上，并返回继承结果与差异。

    基线不存在或不可解析时不阻塞构建：原样返回新资产行，并在差异中标记原因。
    继承只填补新构建仍为默认值的键位，不覆盖新构建已给出的具体绑定。
    """

    path = Path(baseline_path)
    if not path.is_file():
        return rows, AssetManifestDiff(baseline_path=path, baseline_available=False)

    try:
        baseline = load_asset_manifest(path)
    except AssetValidationError as exc:
        return rows, AssetManifestDiff(
            baseline_path=path,
            baseline_available=False,
            baseline_error=str(exc),
        )

    carried: list[str] = []
    conflicts: list[str] = []

    merged = replace(
        rows,
        characters=_carry_index_rows(
            baseline.characters,
            rows.characters,
            "character",
            carried,
            conflicts,
        ),
        weapons=_carry_index_rows(baseline.weapons, rows.weapons, "weapon", carried, conflicts),
        artifact_sets=_carry_index_rows(
            baseline.artifact_sets,
            rows.artifact_sets,
            "artifact-set",
            carried,
            conflicts,
        ),
        artifact_set_bonuses=_carry_bonus_rows(
            baseline.artifact_set_bonuses,
            rows.artifact_set_bonuses,
            carried,
            conflicts,
        ),
        effect_payloads=_carry_effect_rows(
            baseline.effect_payloads,
            rows.effect_payloads,
            carried,
            conflicts,
        ),
    )

    diff = AssetManifestDiff(
        baseline_path=path,
        baseline_available=True,
        baseline_handler_overlay_updated_at=baseline.meta.get(HANDLER_OVERLAY_UPDATED_AT),
        characters=_group_changes(
            _character_fingerprints(baseline),
            _character_fingerprints(merged),
        ),
        weapons=_group_changes(
            _weapon_fingerprints(baseline),
            _weapon_fingerprints(merged),
        ),
        artifact_sets=_group_changes(
            _artifact_set_fingerprints(baseline),
            _artifact_set_fingerprints(merged),
        ),
        carried_bindings=tuple(carried),
        dropped_bindings=_dropped_bindings(baseline, merged),
        binding_conflicts=tuple(conflicts),
    )
    return merged, diff


def _is_placeholder(handler_key: str | None) -> bool:
    """占位键（含 ``*.unimplemented_*``）与空值都不是真实绑定。"""

    return handler_key is None or _PLACEHOLDER_MARKER in handler_key


def _carry_index_rows(
    baseline_items: tuple[Any, ...],
    current_items: tuple[Any, ...],
    kind: str,
    carried: list[str],
    conflicts: list[str],
) -> tuple[Any, ...]:
    """角色、武器、圣遗物套装的 handler 覆盖继承（新构建值为 ``None`` 时填补）。"""

    baseline_handlers = {
        item.asset_key: item.handler_key for item in baseline_items if item.handler_key is not None
    }
    updated: list[Any] = []
    for item in current_items:
        inherited = baseline_handlers.get(item.asset_key)
        if inherited is None:
            updated.append(item)
            continue
        if item.handler_key is None:
            carried.append(f"{kind} {item.asset_key} -> {inherited}")
            updated.append(replace(item, handler_key=inherited))
            continue
        if item.handler_key != inherited:
            conflicts.append(
                f"{kind} {item.asset_key}: 新构建值 {item.handler_key} "
                f"与基线值 {inherited} 不一致，保留新构建值"
            )
        updated.append(item)
    return tuple(updated)


def _carry_bonus_rows(
    baseline_items: tuple[Any, ...],
    current_items: tuple[Any, ...],
    carried: list[str],
    conflicts: list[str],
) -> tuple[Any, ...]:
    """圣遗物套装效果的 handler 覆盖继承（按套装键与件数匹配）。"""

    baseline_handlers = {
        (item.artifact_set_key, item.piece_count): item.handler_key
        for item in baseline_items
        if not _is_placeholder(item.handler_key)
    }
    updated: list[Any] = []
    for item in current_items:
        key = (item.artifact_set_key, item.piece_count)
        inherited = baseline_handlers.get(key)
        if inherited is None:
            updated.append(item)
            continue
        if _is_placeholder(item.handler_key):
            carried.append(
                f"artifact-bonus {item.artifact_set_key}#{item.piece_count} -> {inherited}"
            )
            updated.append(replace(item, handler_key=inherited))
            continue
        if item.handler_key != inherited:
            conflicts.append(
                f"artifact-bonus {item.artifact_set_key}#{item.piece_count}: "
                f"新构建值 {item.handler_key} 与基线值 {inherited} 不一致，保留新构建值"
            )
        updated.append(item)
    return tuple(updated)


def _carry_effect_rows(
    baseline_items: tuple[Any, ...],
    current_items: tuple[Any, ...],
    carried: list[str],
    conflicts: list[str],
) -> tuple[Any, ...]:
    """效果 payload 的 handler 覆盖继承（新构建值为占位键时填补）。"""

    baseline_handlers = {
        item.effect_key: item.handler_key
        for item in baseline_items
        if not _is_placeholder(item.handler_key)
    }
    updated: list[Any] = []
    for item in current_items:
        inherited = baseline_handlers.get(item.effect_key)
        if inherited is None:
            updated.append(item)
            continue
        if _is_placeholder(item.handler_key):
            carried.append(f"effect {item.effect_key} -> {inherited}")
            updated.append(replace(item, handler_key=inherited))
            continue
        if item.handler_key != inherited:
            conflicts.append(
                f"effect {item.effect_key}: 新构建值 {item.handler_key} "
                f"与基线值 {inherited} 不一致，保留新构建值"
            )
        updated.append(item)
    return tuple(updated)


def _dropped_bindings(baseline: AssetManifest, current: AssetManifest) -> tuple[str, ...]:
    """基线中存在、但目标已不在新 manifest 里的真实绑定。"""

    dropped: list[str] = []
    current_character_keys = {item.asset_key for item in current.characters}
    for item in baseline.characters:
        if item.handler_key is not None and item.asset_key not in current_character_keys:
            dropped.append(f"character {item.asset_key} -> {item.handler_key}")

    current_weapon_keys = {item.asset_key for item in current.weapons}
    for item in baseline.weapons:
        if item.handler_key is not None and item.asset_key not in current_weapon_keys:
            dropped.append(f"weapon {item.asset_key} -> {item.handler_key}")

    current_artifact_set_keys = {item.asset_key for item in current.artifact_sets}
    for item in baseline.artifact_sets:
        if item.handler_key is not None and item.asset_key not in current_artifact_set_keys:
            dropped.append(f"artifact-set {item.asset_key} -> {item.handler_key}")

    current_bonus_keys = {
        (item.artifact_set_key, item.piece_count) for item in current.artifact_set_bonuses
    }
    for item in baseline.artifact_set_bonuses:
        key = (item.artifact_set_key, item.piece_count)
        if not _is_placeholder(item.handler_key) and key not in current_bonus_keys:
            dropped.append(
                f"artifact-bonus {item.artifact_set_key}#{item.piece_count} -> {item.handler_key}"
            )

    current_effect_keys = {item.effect_key for item in current.effect_payloads}
    for item in baseline.effect_payloads:
        if not _is_placeholder(item.handler_key) and item.effect_key not in current_effect_keys:
            dropped.append(f"effect {item.effect_key} -> {item.handler_key}")

    return tuple(dropped)


def _group_changes(
    baseline_fingerprints: dict[str, tuple[Any, ...]],
    current_fingerprints: dict[str, tuple[Any, ...]],
) -> AssetGroupChanges:
    added = [key for key in current_fingerprints if key not in baseline_fingerprints]
    removed = [key for key in baseline_fingerprints if key not in current_fingerprints]
    changed = [
        key
        for key, fingerprint in current_fingerprints.items()
        if key in baseline_fingerprints and baseline_fingerprints[key] != fingerprint
    ]
    return AssetGroupChanges(
        added=tuple(sorted(added, key=_stable_sort_key)),
        removed=tuple(sorted(removed, key=_stable_sort_key)),
        changed=tuple(sorted(changed, key=_stable_sort_key)),
    )


def _character_fingerprints(manifest: AssetManifest) -> dict[str, tuple[Any, ...]]:
    stats = _group_sorted(
        manifest.character_level_stats,
        lambda item: item.character_key,
        lambda item: (item.level, item.ascension_phase),
    )
    scalings = _group_sorted(
        manifest.talent_scalings,
        lambda item: item.character_key,
        lambda item: (item.talent_key, item.entry_key),
    )
    effects = _group_sorted(
        manifest.effect_payloads,
        lambda item: item.owner_key,
        lambda item: item.effect_key,
    )
    return {
        item.asset_key: (
            item,
            stats.get(item.asset_key, ()),
            scalings.get(item.asset_key, ()),
            effects.get(item.asset_key, ()),
        )
        for item in manifest.characters
    }


def _weapon_fingerprints(manifest: AssetManifest) -> dict[str, tuple[Any, ...]]:
    stats = _group_sorted(
        manifest.weapon_level_stats,
        lambda item: item.weapon_key,
        lambda item: (item.level, item.ascension_phase),
    )
    effects = _group_sorted(
        manifest.effect_payloads,
        lambda item: item.owner_key,
        lambda item: item.effect_key,
    )
    return {
        item.asset_key: (item, stats.get(item.asset_key, ()), effects.get(item.asset_key, ()))
        for item in manifest.weapons
    }


def _artifact_set_fingerprints(manifest: AssetManifest) -> dict[str, tuple[Any, ...]]:
    bonuses = _group_sorted(
        manifest.artifact_set_bonuses,
        lambda item: item.artifact_set_key,
        lambda item: (item.piece_count, item.handler_key),
    )
    effects = _group_sorted(
        manifest.effect_payloads,
        lambda item: item.owner_key,
        lambda item: item.effect_key,
    )
    return {
        item.asset_key: (item, bonuses.get(item.asset_key, ()), effects.get(item.asset_key, ()))
        for item in manifest.artifact_sets
    }


def _group_sorted[RowT](
    rows: Iterable[RowT],
    group_key: Callable[[RowT], str],
    sort_key: Callable[[RowT], Any],
) -> dict[str, tuple[RowT, ...]]:
    grouped: dict[str, list[RowT]] = {}
    for item in rows:
        grouped.setdefault(group_key(item), []).append(item)
    return {name: tuple(sorted(items, key=sort_key)) for name, items in grouped.items()}


def _stable_sort_key(value: str) -> tuple[int, str]:
    """同类型资产优先按 source_id 数值排序，保证报告顺序稳定可读。"""

    _, _, source_id = value.partition(":")
    if source_id.isdigit():
        return int(source_id), value
    return _NON_NUMERIC_SORT_KEY, value
