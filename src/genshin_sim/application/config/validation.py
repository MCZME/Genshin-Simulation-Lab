from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from genshin_sim.application.config.errors import ConfigError


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{path} 必须是对象")
    return value


def _require_sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ConfigError(f"{path} 必须是列表")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path} 必须是非空字符串")
    return value


def _optional_string(value: Any, path: str, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"{path} 必须是字符串")
    return value


def _require_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{path} 必须是整数")
    return value


def _require_number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"{path} 必须是数字")
    return float(value)


def _require_asset_key(value: Any, expected_type: str, path: str) -> str:
    asset_key = _require_string(value, path)
    prefix = f"{expected_type}:"
    if not asset_key.startswith(prefix) or len(asset_key) <= len(prefix):
        raise ConfigError(f"{path} 必须使用 {prefix}<source_id> 格式")
    return asset_key
