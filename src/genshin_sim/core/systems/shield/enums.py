from __future__ import annotations

from enum import StrEnum


class ShieldElement(StrEnum):
    NONE = "none"
    PYRO = "pyro"
    HYDRO = "hydro"
    ELECTRO = "electro"
    CRYO = "cryo"
    ANEMO = "anemo"
    GEO = "geo"
    DENDRO = "dendro"


class ShieldGrantPolicy(StrEnum):
    REPLACE = "replace"
    REFRESH_REPLACE = "refresh_replace"
    ADD_CAPPED_REFRESH = "add_capped_refresh"
    KEEP_STRONGER_REFRESH = "keep_stronger_refresh"
    COEXIST = "coexist"


class ShieldRemovalReason(StrEnum):
    DEPLETED = "depleted"
    EXPIRED = "expired"
    REPLACED = "replaced"
    DISPELLED = "dispelled"
    OWNER_REMOVED = "owner_removed"


class ShieldGrantOutcome(StrEnum):
    CREATED = "created"
    REPLACED = "replaced"
    REFRESHED = "refreshed"
    STACKED = "stacked"
    KEPT_EXISTING = "kept_existing"


class ShieldChangeReason(StrEnum):
    GRANTED = "granted"
    ABSORBED = "absorbed"
    STACKED = "stacked"
    REFRESHED = "refreshed"


class ShieldProtectionKind(StrEnum):
    ACTIVE_TEAM = "active_team"
    CHARACTER = "character"
