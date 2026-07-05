"""只读资产库的 SQLite 实现。"""

from genshin_sim.infrastructure.assets_sqlite.repository import SQLiteAssetRepository
from genshin_sim.infrastructure.assets_sqlite.schema import (
    ASSET_SCHEMA_VERSION,
    init_asset_database,
    validate_asset_database,
)
from genshin_sim.infrastructure.assets_sqlite.writer import (
    SQLiteAssetDataWriter,
    write_minimal_static_asset_database,
)

__all__ = [
    "ASSET_SCHEMA_VERSION",
    "SQLiteAssetRepository",
    "SQLiteAssetDataWriter",
    "init_asset_database",
    "validate_asset_database",
    "write_minimal_static_asset_database",
]
