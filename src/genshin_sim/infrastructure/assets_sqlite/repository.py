from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from genshin_sim.assets import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    AssetDbInfo,
    AssetNotFoundError,
    AssetValidationError,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    HandlerBinding,
    TalentScalingEntry,
    WeaponAsset,
    WeaponLevelStats,
)

# 可选择突破前/突破后属性的等级。
_ASCENDABLE_LEVELS = frozenset({20, 40, 50, 60, 70, 80})


class SQLiteAssetRepository:
    """从 SQLite 资产数据库读取资产模型。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def get_meta(self) -> dict[str, str]:
        with closing(self._connect()) as connection:
            return {
                str(row["key"]): str(row["value"])
                for row in connection.execute("SELECT key, value FROM asset_db_meta ORDER BY key")
            }

    def get_info(self) -> AssetDbInfo:
        with closing(self._connect()) as connection:
            return AssetDbInfo(
                meta=self.get_meta(),
                character_count=_count(connection, "characters"),
                weapon_count=_count(connection, "weapons"),
                artifact_set_count=_count(connection, "artifact_sets"),
            )

    def list_characters(self) -> tuple[CharacterAsset, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT asset_key, source_id, name, element, weapon_type, rarity,
                       burst_energy_cost, handler_key
                FROM characters
                ORDER BY asset_key
                """
            ).fetchall()
        return tuple(_character_from_row(row) for row in rows)

    def get_character(self, character_key: str) -> CharacterAsset:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT asset_key, source_id, name, element, weapon_type, rarity,
                       burst_energy_cost, handler_key
                FROM characters
                WHERE asset_key = ?
                """,
                (character_key,),
            ).fetchone()
        if row is None:
            raise AssetNotFoundError(f"character not found: {character_key}")
        return _character_from_row(row)

    def get_character_level_stats(
        self,
        character_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> CharacterLevelStats:
        phase_order = "DESC" if ascended or level not in _ASCENDABLE_LEVELS else "ASC"
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"""
                SELECT character_key, level, ascension_phase, base_hp, base_atk, base_def,
                       ascension_stat, ascension_value
                FROM character_level_stats
                WHERE character_key = ? AND level = ?
                ORDER BY ascension_phase {phase_order}
                LIMIT 1
                """,
                (character_key, level),
            ).fetchone()
        if row is None:
            raise AssetNotFoundError(
                f"character level stats not found: {character_key} level {level}"
            )
        return CharacterLevelStats(
            character_key=str(row["character_key"]),
            level=int(row["level"]),
            ascension_phase=int(row["ascension_phase"]),
            base_hp=float(row["base_hp"]),
            base_atk=float(row["base_atk"]),
            base_def=float(row["base_def"]),
            ascension_stat=_optional_str(row["ascension_stat"]),
            ascension_value=_optional_float(row["ascension_value"]),
        )

    def list_weapons(self, weapon_type: str | None = None) -> tuple[WeaponAsset, ...]:
        sql = """
            SELECT asset_key, source_id, name, weapon_type, rarity, handler_key
            FROM weapons
        """
        params: tuple[object, ...] = ()
        if weapon_type is not None:
            sql += " WHERE weapon_type = ?"
            params = (weapon_type,)
        sql += " ORDER BY asset_key"

        with closing(self._connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return tuple(_weapon_from_row(row) for row in rows)

    def get_weapon(self, weapon_key: str) -> WeaponAsset:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT asset_key, source_id, name, weapon_type, rarity, handler_key
                FROM weapons
                WHERE asset_key = ?
                """,
                (weapon_key,),
            ).fetchone()
        if row is None:
            raise AssetNotFoundError(f"weapon not found: {weapon_key}")
        return _weapon_from_row(row)

    def get_weapon_level_stats(
        self,
        weapon_key: str,
        level: int,
        *,
        ascended: bool = True,
    ) -> WeaponLevelStats:
        phase_order = "DESC" if ascended or level not in _ASCENDABLE_LEVELS else "ASC"
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"""
                SELECT weapon_key, level, ascension_phase, base_atk, secondary_stat,
                       secondary_value
                FROM weapon_level_stats
                WHERE weapon_key = ? AND level = ?
                ORDER BY ascension_phase {phase_order}
                LIMIT 1
                """,
                (weapon_key, level),
            ).fetchone()
        if row is None:
            raise AssetNotFoundError(f"weapon level stats not found: {weapon_key} level {level}")
        return WeaponLevelStats(
            weapon_key=str(row["weapon_key"]),
            level=int(row["level"]),
            ascension_phase=int(row["ascension_phase"]),
            base_atk=float(row["base_atk"]),
            secondary_stat=_optional_str(row["secondary_stat"]),
            secondary_value=_optional_float(row["secondary_value"]),
        )

    def list_artifact_sets(self) -> tuple[ArtifactSetAsset, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT asset_key, source_id, name, handler_key
                FROM artifact_sets
                ORDER BY asset_key
                """
            ).fetchall()
        return tuple(_artifact_set_from_row(row) for row in rows)

    def get_artifact_set(self, artifact_set_key: str) -> ArtifactSetAsset:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT asset_key, source_id, name, handler_key
                FROM artifact_sets
                WHERE asset_key = ?
                """,
                (artifact_set_key,),
            ).fetchone()
        if row is None:
            raise AssetNotFoundError(f"artifact set not found: {artifact_set_key}")
        return _artifact_set_from_row(row)

    def get_artifact_set_bonuses(
        self,
        artifact_set_key: str,
        piece_count: int | None = None,
    ) -> tuple[ArtifactSetBonus, ...]:
        sql = """
            SELECT artifact_set_key, piece_count, handler_key, params_json
            FROM artifact_set_bonuses
            WHERE artifact_set_key = ?
        """
        params: tuple[object, ...] = (artifact_set_key,)
        if piece_count is not None:
            sql += " AND piece_count = ?"
            params = (artifact_set_key, piece_count)
        sql += " ORDER BY piece_count, handler_key"

        with closing(self._connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return tuple(
            ArtifactSetBonus(
                artifact_set_key=str(row["artifact_set_key"]),
                piece_count=int(row["piece_count"]),
                handler_key=str(row["handler_key"]),
                params=_load_json_object(
                    str(row["params_json"]),
                    "artifact_set_bonuses.params_json",
                ),
            )
            for row in rows
        )

    def get_talent_scalings(
        self,
        character_key: str,
        talent_key: str,
    ) -> tuple[TalentScalingEntry, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, character_key, talent_key, entry_key, label, scaling_json, tags_json
                FROM talent_scaling_entries
                WHERE character_key = ? AND talent_key = ?
                ORDER BY id
                """,
                (character_key, talent_key),
            ).fetchall()
        return tuple(
            TalentScalingEntry(
                entry_id=int(row["id"]),
                character_key=str(row["character_key"]),
                talent_key=str(row["talent_key"]),
                entry_key=str(row["entry_key"]),
                label=str(row["label"]),
                scaling=_load_json_object(
                    str(row["scaling_json"]),
                    "talent_scaling_entries.scaling_json",
                ),
                tags=_load_tags(row["tags_json"]),
            )
            for row in rows
        )

    def get_effect_payloads(
        self,
        owner_key: str,
        effect_kind: str | None = None,
    ) -> tuple[EffectPayload, ...]:
        sql = """
            SELECT effect_key, owner_type, owner_key, effect_kind, unlock_key, handler_key,
                   params_json
            FROM effect_payloads
            WHERE owner_key = ?
        """
        params: tuple[object, ...] = (owner_key,)
        if effect_kind is not None:
            sql += " AND effect_kind = ?"
            params = (owner_key, effect_kind)
        sql += " ORDER BY effect_key"

        with closing(self._connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return tuple(
            EffectPayload(
                effect_key=str(row["effect_key"]),
                owner_type=str(row["owner_type"]),
                owner_key=str(row["owner_key"]),
                effect_kind=str(row["effect_kind"]),
                unlock_key=_optional_str(row["unlock_key"]),
                handler_key=str(row["handler_key"]),
                params=_load_json_object(str(row["params_json"]), "effect_payloads.params_json"),
            )
            for row in rows
        )

    def get_handler_binding(
        self,
        kind: str,
        key: str,
        pieces: int | None = None,
    ) -> HandlerBinding:
        with closing(self._connect()) as connection:
            if kind == "character":
                row = connection.execute(
                    "SELECT handler_key FROM characters WHERE asset_key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    raise AssetNotFoundError(f"character not found: {key}")
                return HandlerBinding(
                    kind=kind,
                    key=key,
                    handler_key=_optional_str(row["handler_key"]),
                )
            if kind == "weapon":
                row = connection.execute(
                    "SELECT handler_key FROM weapons WHERE asset_key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    raise AssetNotFoundError(f"weapon not found: {key}")
                return HandlerBinding(
                    kind=kind,
                    key=key,
                    handler_key=_optional_str(row["handler_key"]),
                )
            if kind == "artifact-set":
                row = connection.execute(
                    "SELECT handler_key FROM artifact_sets WHERE asset_key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    raise AssetNotFoundError(f"artifact set not found: {key}")
                return HandlerBinding(
                    kind=kind,
                    key=key,
                    handler_key=_optional_str(row["handler_key"]),
                )
            if kind == "artifact-bonus":
                if pieces is None:
                    raise AssetValidationError("artifact-bonus 需要 --pieces")
                row = connection.execute(
                    """
                    SELECT handler_key FROM artifact_set_bonuses
                    WHERE artifact_set_key = ? AND piece_count = ?
                    """,
                    (key, pieces),
                ).fetchone()
                if row is None:
                    raise AssetNotFoundError(f"artifact set bonus not found: {key}@{pieces}")
                return HandlerBinding(
                    kind=kind,
                    key=key,
                    pieces=pieces,
                    handler_key=str(row["handler_key"]),
                )
            if kind == "effect":
                row = connection.execute(
                    """
                    SELECT effect_kind, handler_key FROM effect_payloads
                    WHERE effect_key = ?
                    """,
                    (key,),
                ).fetchone()
                if row is None:
                    raise AssetNotFoundError(f"effect payload not found: {key}")
                return HandlerBinding(
                    kind=kind,
                    key=key,
                    effect_kind=str(row["effect_kind"]),
                    handler_key=str(row["handler_key"]),
                )
        raise AssetValidationError(f"不支持的 handler 绑定类别：{kind}")

    def set_handler_binding(
        self,
        kind: str,
        key: str,
        handler_key: str | None,
        pieces: int | None = None,
    ) -> None:
        binding = self.get_handler_binding(kind, key, pieces)
        del binding
        if kind == "character":
            sql = "UPDATE characters SET handler_key = ? WHERE asset_key = ?"
            params: tuple[object, ...] = (handler_key, key)
        elif kind == "weapon":
            sql = "UPDATE weapons SET handler_key = ? WHERE asset_key = ?"
            params = (handler_key, key)
        elif kind == "artifact-set":
            sql = "UPDATE artifact_sets SET handler_key = ? WHERE asset_key = ?"
            params = (handler_key, key)
        elif kind == "artifact-bonus":
            if pieces is None:
                raise AssetValidationError("artifact-bonus 需要 --pieces")
            sql = """
                UPDATE artifact_set_bonuses SET handler_key = ?
                WHERE artifact_set_key = ? AND piece_count = ?
            """
            params = (handler_key, key, pieces)
        elif kind == "effect":
            sql = "UPDATE effect_payloads SET handler_key = ? WHERE effect_key = ?"
            params = (handler_key, key)
        else:
            raise AssetValidationError(f"不支持的 handler 绑定类别：{kind}")
        with closing(self._connect(readonly=False)) as connection:
            connection.execute(sql, params)
            connection.commit()

    def list_handler_bindings(
        self,
        kind: str,
        owner_key: str | None = None,
    ) -> tuple[HandlerBinding, ...]:
        with closing(self._connect()) as connection:
            if kind == "character":
                rows = connection.execute(
                    "SELECT asset_key, handler_key FROM characters ORDER BY asset_key"
                ).fetchall()
                return tuple(
                    HandlerBinding(
                        kind=kind,
                        key=str(row["asset_key"]),
                        handler_key=_optional_str(row["handler_key"]),
                    )
                    for row in rows
                )
            if kind == "weapon":
                rows = connection.execute(
                    "SELECT asset_key, handler_key FROM weapons ORDER BY asset_key"
                ).fetchall()
                return tuple(
                    HandlerBinding(
                        kind=kind,
                        key=str(row["asset_key"]),
                        handler_key=_optional_str(row["handler_key"]),
                    )
                    for row in rows
                )
            if kind == "artifact-set":
                rows = connection.execute(
                    "SELECT asset_key, handler_key FROM artifact_sets ORDER BY asset_key"
                ).fetchall()
                return tuple(
                    HandlerBinding(
                        kind=kind,
                        key=str(row["asset_key"]),
                        handler_key=_optional_str(row["handler_key"]),
                    )
                    for row in rows
                )
            if kind == "artifact-bonus":
                rows = connection.execute(
                    """
                    SELECT artifact_set_key, piece_count, handler_key
                    FROM artifact_set_bonuses
                    ORDER BY artifact_set_key, piece_count
                    """
                ).fetchall()
                return tuple(
                    HandlerBinding(
                        kind=kind,
                        key=str(row["artifact_set_key"]),
                        pieces=int(row["piece_count"]),
                        handler_key=str(row["handler_key"]),
                    )
                    for row in rows
                )
            if kind == "effect":
                sql = """
                    SELECT effect_key, effect_kind, handler_key
                    FROM effect_payloads
                """
                params: tuple[object, ...] = ()
                if owner_key is not None:
                    sql += " WHERE owner_key = ?"
                    params = (owner_key,)
                sql += " ORDER BY effect_key"
                rows = connection.execute(sql, params).fetchall()
                return tuple(
                    HandlerBinding(
                        kind=kind,
                        key=str(row["effect_key"]),
                        effect_kind=str(row["effect_kind"]),
                        handler_key=str(row["handler_key"]),
                    )
                    for row in rows
                )
        raise AssetValidationError(f"不支持的 handler 绑定类别：{kind}")

    def _connect(self, *, readonly: bool = True) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise AssetValidationError(f"asset database does not exist: {self.db_path}")
        try:
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            if readonly:
                connection.execute("PRAGMA query_only = ON")
        except sqlite3.Error as exc:
            raise AssetValidationError(f"cannot open asset database: {self.db_path}") from exc
        return connection


def _count(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"])


def _character_from_row(row: sqlite3.Row) -> CharacterAsset:
    return CharacterAsset(
        asset_key=str(row["asset_key"]),
        source_id=str(row["source_id"]),
        name=str(row["name"]),
        element=str(row["element"]),
        weapon_type=str(row["weapon_type"]),
        rarity=int(row["rarity"]),
        burst_energy_cost=float(row["burst_energy_cost"]),
        handler_key=_optional_str(row["handler_key"]),
    )


def _weapon_from_row(row: sqlite3.Row) -> WeaponAsset:
    return WeaponAsset(
        asset_key=str(row["asset_key"]),
        source_id=str(row["source_id"]),
        name=str(row["name"]),
        weapon_type=str(row["weapon_type"]),
        rarity=int(row["rarity"]),
        handler_key=_optional_str(row["handler_key"]),
    )


def _artifact_set_from_row(row: sqlite3.Row) -> ArtifactSetAsset:
    return ArtifactSetAsset(
        asset_key=str(row["asset_key"]),
        source_id=str(row["source_id"]),
        name=str(row["name"]),
        handler_key=_optional_str(row["handler_key"]),
    )


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _load_json_object(raw: str, field_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssetValidationError(f"{field_name} must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise AssetValidationError(f"{field_name} must be a JSON object")
    return payload


def _load_tags(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise AssetValidationError("talent_scaling_entries.tags_json must be valid JSON") from exc
    if not isinstance(payload, list):
        raise AssetValidationError("talent_scaling_entries.tags_json must be a JSON list")
    return tuple(str(item) for item in payload)
