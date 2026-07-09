"""只读资产库的 SQLite 实现。"""

from genshin_sim.infrastructure.assets_sqlite.manifest import (
    ASSET_MANIFEST_KIND,
    ASSET_MANIFEST_SCHEMA_VERSION,
    AssetManifest,
    build_asset_database_from_manifest,
    load_asset_manifest,
)
from genshin_sim.infrastructure.assets_sqlite.manifest_audit import (
    AssetManifestAuditIssue,
    AssetManifestAuditReport,
    audit_asset_manifest,
    audit_loaded_asset_manifest,
)
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
    "ASSET_MANIFEST_KIND",
    "ASSET_MANIFEST_SCHEMA_VERSION",
    "ASSET_SCHEMA_VERSION",
    "AssetManifest",
    "AssetManifestAuditIssue",
    "AssetManifestAuditReport",
    "SQLiteAssetRepository",
    "SQLiteAssetDataWriter",
    "audit_asset_manifest",
    "audit_loaded_asset_manifest",
    "build_asset_database_from_manifest",
    "init_asset_database",
    "load_asset_manifest",
    "validate_asset_database",
    "write_minimal_static_asset_database",
]
