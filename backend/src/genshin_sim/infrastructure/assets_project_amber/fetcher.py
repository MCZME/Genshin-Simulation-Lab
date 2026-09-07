from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from genshin_sim.assets import AssetValidationError

PROJECT_AMBER_SOURCE_NAME = "project-amber-yatta"
PROJECT_AMBER_LANGUAGE = "chs"
PROJECT_AMBER_SOURCE_VERSION = "default"
PROJECT_AMBER_BASE_URL = "https://gi.yatta.moe/api/v2/chs"
PROJECT_AMBER_STATIC_URL = "https://gi.yatta.moe/api/v2/static"
PROJECT_AMBER_CACHE_SCHEMA_VERSION = 1
_USER_AGENT = "Genshin-Sim-Lab asset-source-fetcher/1"


class JsonHttpClient(Protocol):
    def get_json(self, url: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ProjectAmberSourceCacheSummary:
    output_dir: Path
    source_name: str
    source_version: str
    language: str
    fetched_at: str
    content_hash: str
    character_count: int
    weapon_count: int
    artifact_set_count: int
    character_detail_count: int
    weapon_detail_count: int
    artifact_set_detail_count: int
    file_count: int


class UrllibJsonHttpClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.retry_delay_seconds = retry_delay_seconds

    def get_json(self, url: str) -> Mapping[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = json.load(response)
                break
            except (OSError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    raise AssetValidationError(
                        f"资产源请求失败：{url}；已重试 {self.max_attempts} 次；最后错误：{exc}"
                    ) from exc
                time.sleep(self.retry_delay_seconds)
        else:
            raise AssetValidationError(f"资产源请求失败：{url}") from last_error
        if not isinstance(payload, Mapping):
            raise AssetValidationError(f"资产源响应必须是 JSON 对象：{url}")
        return payload


def fetch_project_amber_source_cache(
    output_dir: str | Path,
    *,
    character_ids: Iterable[str] = (),
    weapon_ids: Iterable[str] = (),
    artifact_set_ids: Iterable[str] = (),
    include_all_details: bool = False,
    client: JsonHttpClient | None = None,
    fetched_at: datetime | None = None,
) -> ProjectAmberSourceCacheSummary:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    resolved_client = client or UrllibJsonHttpClient()
    resolved_fetched_at = fetched_at or datetime.now(UTC)
    files: list[dict[str, object]] = []

    avatar_index = _fetch_and_write(
        client=resolved_client,
        url=f"{PROJECT_AMBER_BASE_URL}/avatar",
        output_path=target_dir / "avatar" / "index.json",
        cache_root=target_dir,
        files=files,
    )
    indexed_character_ids = _extract_item_ids(avatar_index, "avatar/index")
    selected_character_ids = _resolve_detail_ids(
        indexed_ids=indexed_character_ids,
        requested_ids=character_ids,
        include_all_details=include_all_details,
        label="角色",
    )
    for character_id in selected_character_ids:
        _fetch_and_write(
            client=resolved_client,
            url=f"{PROJECT_AMBER_BASE_URL}/avatar/{character_id}",
            output_path=target_dir / "avatar" / f"{character_id}.json",
            cache_root=target_dir,
            files=files,
            reuse_existing=True,
        )

    weapon_index = _fetch_and_write(
        client=resolved_client,
        url=f"{PROJECT_AMBER_BASE_URL}/weapon",
        output_path=target_dir / "weapon" / "index.json",
        cache_root=target_dir,
        files=files,
    )
    indexed_weapon_ids = _extract_item_ids(weapon_index, "weapon/index")
    selected_weapon_ids = _resolve_detail_ids(
        indexed_ids=indexed_weapon_ids,
        requested_ids=weapon_ids,
        include_all_details=include_all_details,
        label="武器",
    )
    for weapon_id in selected_weapon_ids:
        _fetch_and_write(
            client=resolved_client,
            url=f"{PROJECT_AMBER_BASE_URL}/weapon/{weapon_id}",
            output_path=target_dir / "weapon" / f"{weapon_id}.json",
            cache_root=target_dir,
            files=files,
            reuse_existing=True,
        )

    reliquary_index = _fetch_and_write(
        client=resolved_client,
        url=f"{PROJECT_AMBER_BASE_URL}/reliquary",
        output_path=target_dir / "reliquary" / "index.json",
        cache_root=target_dir,
        files=files,
    )
    indexed_artifact_set_ids = _extract_item_ids(reliquary_index, "reliquary/index")
    selected_artifact_set_ids = _resolve_detail_ids(
        indexed_ids=indexed_artifact_set_ids,
        requested_ids=artifact_set_ids,
        include_all_details=include_all_details,
        label="圣遗物套装",
    )
    for artifact_set_id in selected_artifact_set_ids:
        _fetch_and_write(
            client=resolved_client,
            url=f"{PROJECT_AMBER_BASE_URL}/reliquary/{artifact_set_id}",
            output_path=target_dir / "reliquary" / f"{artifact_set_id}.json",
            cache_root=target_dir,
            files=files,
            reuse_existing=True,
        )

    _fetch_and_write(
        client=resolved_client,
        url=f"{PROJECT_AMBER_STATIC_URL}/avatarCurve",
        output_path=target_dir / "static" / "avatarCurve.json",
        cache_root=target_dir,
        files=files,
    )
    _fetch_and_write(
        client=resolved_client,
        url=f"{PROJECT_AMBER_STATIC_URL}/weaponCurve",
        output_path=target_dir / "static" / "weaponCurve.json",
        cache_root=target_dir,
        files=files,
    )

    content_hash = _content_hash(files)
    manifest = {
        "schema_version": PROJECT_AMBER_CACHE_SCHEMA_VERSION,
        "kind": "project_amber_source_cache",
        "source_name": PROJECT_AMBER_SOURCE_NAME,
        "source_version": PROJECT_AMBER_SOURCE_VERSION,
        "language": PROJECT_AMBER_LANGUAGE,
        "base_url": PROJECT_AMBER_BASE_URL,
        "static_url": PROJECT_AMBER_STATIC_URL,
        "fetched_at": resolved_fetched_at.isoformat(timespec="seconds"),
        "content_hash": content_hash,
        "counts": {
            "characters": len(indexed_character_ids),
            "weapons": len(indexed_weapon_ids),
            "artifact_sets": len(indexed_artifact_set_ids),
            "character_details": len(selected_character_ids),
            "weapon_details": len(selected_weapon_ids),
            "artifact_set_details": len(selected_artifact_set_ids),
        },
        "files": files,
    }
    _write_json(target_dir / "fetch_manifest.json", manifest)

    return ProjectAmberSourceCacheSummary(
        output_dir=target_dir,
        source_name=PROJECT_AMBER_SOURCE_NAME,
        source_version=PROJECT_AMBER_SOURCE_VERSION,
        language=PROJECT_AMBER_LANGUAGE,
        fetched_at=str(manifest["fetched_at"]),
        content_hash=content_hash,
        character_count=len(indexed_character_ids),
        weapon_count=len(indexed_weapon_ids),
        artifact_set_count=len(indexed_artifact_set_ids),
        character_detail_count=len(selected_character_ids),
        weapon_detail_count=len(selected_weapon_ids),
        artifact_set_detail_count=len(selected_artifact_set_ids),
        file_count=len(files),
    )


def _fetch_and_write(
    *,
    client: JsonHttpClient,
    url: str,
    output_path: Path,
    cache_root: Path,
    files: list[dict[str, object]],
    reuse_existing: bool = False,
) -> Mapping[str, Any]:
    if reuse_existing:
        cached = _read_existing_cache_file(output_path, url)
        if cached is not None:
            payload, text = cached
            _append_file_record(
                url=url,
                output_path=output_path,
                cache_root=cache_root,
                text=text,
                files=files,
            )
            return payload

    payload = client.get_json(url)
    _validate_project_amber_response(payload, url)
    text = _write_json(output_path, payload)
    _append_file_record(
        url=url,
        output_path=output_path,
        cache_root=cache_root,
        text=text,
        files=files,
    )
    return payload


def _append_file_record(
    *,
    url: str,
    output_path: Path,
    cache_root: Path,
    text: str,
    files: list[dict[str, object]],
) -> None:
    files.append(
        {
            "url": url,
            "path": output_path.relative_to(cache_root).as_posix(),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "size_bytes": len(text.encode("utf-8")),
        }
    )


def _validate_project_amber_response(payload: Mapping[str, Any], url: str) -> None:
    response = payload.get("response")
    if response is not None and response != 200:
        raise AssetValidationError(f"资产源响应状态不是 200：{url} response={response!r}")
    if "data" not in payload:
        raise AssetValidationError(f"资产源响应缺少 data 字段：{url}")


def _read_existing_cache_file(path: Path, url: str) -> tuple[Mapping[str, Any], str] | None:
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
    except OSError, json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    try:
        _validate_project_amber_response(payload, url)
    except AssetValidationError:
        return None
    return payload, text


def _extract_item_ids(payload: Mapping[str, Any], label: str) -> tuple[str, ...]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise AssetValidationError(f"{label} 的 data 必须是 JSON 对象")
    items = data.get("items")
    if not isinstance(items, Mapping):
        raise AssetValidationError(f"{label} 的 data.items 必须是 JSON 对象")
    return tuple(sorted(str(item_id) for item_id in items))


def _resolve_detail_ids(
    *,
    indexed_ids: tuple[str, ...],
    requested_ids: Iterable[str],
    include_all_details: bool,
    label: str,
) -> tuple[str, ...]:
    if include_all_details:
        return indexed_ids
    requested = tuple(dict.fromkeys(str(item_id) for item_id in requested_ids))
    missing = sorted(set(requested) - set(indexed_ids))
    if missing:
        raise AssetValidationError(f"请求抓取的{label} ID 不在索引中：{', '.join(missing)}")
    return requested


def _write_json(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def _content_hash(files: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda file: str(file["path"])):
        digest.update(str(item["path"]).encode("utf-8"))
        digest.update(str(item["sha256"]).encode("utf-8"))
    return digest.hexdigest()
