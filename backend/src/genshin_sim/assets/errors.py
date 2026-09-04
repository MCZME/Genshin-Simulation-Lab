"""Asset repository and validation errors."""


class AssetError(Exception):
    """Base error for asset access and validation."""


class AssetNotFoundError(AssetError, LookupError):
    """Requested asset was not found."""


class AssetValidationError(AssetError, ValueError):
    """Asset payload or database structure is invalid."""
