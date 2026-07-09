from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from genshin_sim.infrastructure.assets_project_amber import fetch_project_amber_source_cache
from genshin_sim.infrastructure.assets_project_amber.fetcher import UrllibJsonHttpClient


def test_fetch_project_amber_source_cache_writes_raw_files(tmp_path):
    client = FakeJsonClient(
        {
            "https://gi.yatta.moe/api/v2/chs/avatar": {
                "response": 200,
                "data": {"items": {"75": {"name": "芙宁娜"}}},
            },
            "https://gi.yatta.moe/api/v2/chs/avatar/75": {
                "response": 200,
                "data": {"id": 75, "name": "芙宁娜"},
            },
            "https://gi.yatta.moe/api/v2/chs/weapon": {
                "response": 200,
                "data": {"items": {"11512": {"name": "静水流涌之辉"}}},
            },
            "https://gi.yatta.moe/api/v2/chs/weapon/11512": {
                "response": 200,
                "data": {"id": 11512, "name": "静水流涌之辉"},
            },
            "https://gi.yatta.moe/api/v2/static/avatarCurve": {
                "response": 200,
                "data": {"1": {"curveInfos": {}}},
            },
            "https://gi.yatta.moe/api/v2/static/weaponCurve": {
                "response": 200,
                "data": {"1": {"curveInfos": {}}},
            },
        }
    )

    summary = fetch_project_amber_source_cache(
        tmp_path / "cache",
        include_all_details=True,
        client=client,
        fetched_at=datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
    )

    assert summary.character_count == 1
    assert summary.weapon_count == 1
    assert summary.file_count == 6
    assert (tmp_path / "cache" / "avatar" / "index.json").exists()
    assert (tmp_path / "cache" / "avatar" / "75.json").exists()
    assert (tmp_path / "cache" / "weapon" / "11512.json").exists()

    manifest = json.loads((tmp_path / "cache" / "fetch_manifest.json").read_text("utf-8"))
    assert manifest["source_name"] == "project-amber-yatta"
    assert manifest["source_version"] == "default"
    assert manifest["counts"] == {
        "characters": 1,
        "weapons": 1,
        "character_details": 1,
        "weapon_details": 1,
    }
    assert {item["path"] for item in manifest["files"]} == {
        "avatar/index.json",
        "avatar/75.json",
        "weapon/index.json",
        "weapon/11512.json",
        "static/avatarCurve.json",
        "static/weaponCurve.json",
    }
    assert all("vh=" not in url for url in client.requested_urls)


def test_fetch_project_amber_source_cache_skips_details_by_default(tmp_path):
    client = FakeJsonClient(
        {
            "https://gi.yatta.moe/api/v2/chs/avatar": {
                "response": 200,
                "data": {"items": {"75": {"name": "芙宁娜"}}},
            },
            "https://gi.yatta.moe/api/v2/chs/weapon": {
                "response": 200,
                "data": {"items": {"11512": {"name": "静水流涌之辉"}}},
            },
            "https://gi.yatta.moe/api/v2/static/avatarCurve": {
                "response": 200,
                "data": {"1": {"curveInfos": {}}},
            },
            "https://gi.yatta.moe/api/v2/static/weaponCurve": {
                "response": 200,
                "data": {"1": {"curveInfos": {}}},
            },
        }
    )

    summary = fetch_project_amber_source_cache(tmp_path / "cache", client=client)

    assert summary.character_detail_count == 0
    assert summary.weapon_detail_count == 0
    assert summary.file_count == 4
    assert not (tmp_path / "cache" / "avatar" / "75.json").exists()
    assert not (tmp_path / "cache" / "weapon" / "11512.json").exists()


def test_fetch_project_amber_source_cache_reuses_existing_detail_files(tmp_path):
    cache_dir = tmp_path / "cache"
    (cache_dir / "avatar").mkdir(parents=True)
    (cache_dir / "weapon").mkdir(parents=True)
    (cache_dir / "avatar" / "75.json").write_text(
        json.dumps({"response": 200, "data": {"id": 75, "name": "芙宁娜"}}),
        encoding="utf-8",
    )
    (cache_dir / "weapon" / "11512.json").write_text(
        json.dumps({"response": 200, "data": {"id": 11512, "name": "静水流涌之辉"}}),
        encoding="utf-8",
    )
    client = FakeJsonClient(
        {
            "https://gi.yatta.moe/api/v2/chs/avatar": {
                "response": 200,
                "data": {"items": {"75": {"name": "芙宁娜"}}},
            },
            "https://gi.yatta.moe/api/v2/chs/weapon": {
                "response": 200,
                "data": {"items": {"11512": {"name": "静水流涌之辉"}}},
            },
            "https://gi.yatta.moe/api/v2/static/avatarCurve": {
                "response": 200,
                "data": {"1": {"curveInfos": {}}},
            },
            "https://gi.yatta.moe/api/v2/static/weaponCurve": {
                "response": 200,
                "data": {"1": {"curveInfos": {}}},
            },
        }
    )

    summary = fetch_project_amber_source_cache(cache_dir, include_all_details=True, client=client)

    assert summary.character_detail_count == 1
    assert summary.weapon_detail_count == 1
    assert summary.file_count == 6
    assert "https://gi.yatta.moe/api/v2/chs/avatar/75" not in client.requested_urls
    assert "https://gi.yatta.moe/api/v2/chs/weapon/11512" not in client.requested_urls


def test_urllib_json_client_retries_transient_failures(monkeypatch):
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        del request, timeout
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("temporary reset")
        return FakeHttpResponse(b'{"response":200,"data":{}}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    client = UrllibJsonHttpClient(max_attempts=2)

    assert client.get_json("https://example.test/data")["response"] == 200
    assert calls["count"] == 2


class FakeJsonClient:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses
        self.requested_urls: list[str] = []

    def get_json(self, url: str) -> dict[str, Any]:
        self.requested_urls.append(url)
        return self.responses[url]


class FakeHttpResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        return False

    def read(self) -> bytes:
        return self.payload
