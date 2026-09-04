"""结果查询 HTTP 路由单元测试。"""

from fastapi.testclient import TestClient

from genshin_sim.application import RecordedEvent, RunDetail, SimulationRunSummary
from genshin_sim.server import create_app


def _run(
    session_id: str,
    *,
    state: str = "completed",
    events: tuple[RecordedEvent, ...] = (),
) -> RunDetail:
    return RunDetail(
        session_id=session_id,
        state=state,
        input_snapshot={
            "meta": {"name": "主配队"},
            "team": [],
        },
        initial_snapshot={"frame": 0},
        summary=SimulationRunSummary(
            stop_reason="INPUT_EXHAUSTED",
            end_frame=600,
            frames_run=600,
        )
        if state == "completed"
        else None,
        events=events,
        error_code=None,
        error_message=None,
        created_at="2026-08-17T12:00:00+00:00",
        started_at="2026-08-17T12:00:01+00:00",
        finished_at="2026-08-17T12:00:08+00:00",
    )


def _run_at(
    session_id: str,
    *,
    name: str,
    state: str = "completed",
    created_at: str,
) -> RunDetail:
    return RunDetail(
        session_id=session_id,
        state=state,
        input_snapshot={"meta": {"name": name}, "team": []},
        initial_snapshot={"frame": 0},
        summary=SimulationRunSummary(
            stop_reason="INPUT_EXHAUSTED",
            end_frame=600,
            frames_run=600,
        )
        if state == "completed"
        else None,
        events=(),
        error_code=None,
        error_message=None,
        created_at=created_at,
        started_at=None,
        finished_at=None,
    )


def test_results_list_and_detail_hide_sensitive_fields(application_facade) -> None:
    events = (
        RecordedEvent(frame=1, event_type="DAMAGE_DEALT", data={"value": 1}),
        RecordedEvent(frame=2, event_type="DAMAGE_DEALT", data={"value": 2}),
    )
    run = _run("session-1", events=events)
    app = create_app(application_facade(results=(run,)))

    with TestClient(app) as client:
        listed = client.get("/api/v1/results")
        detail = client.get("/api/v1/results/session-1")

    assert listed.status_code == 200
    assert listed.json()["items"][0]["session_id"] == "session-1"
    assert listed.json()["items"][0]["name"] == "主配队"

    assert detail.status_code == 200
    body = detail.json()
    assert body["event_count"] == 2
    assert body["summary"]["stop_reason"] == "INPUT_EXHAUSTED"
    assert "events" not in body
    assert "input_snapshot" not in body
    assert "initial_snapshot" not in body


def test_results_events_pagination_returns_total(application_facade) -> None:
    run = _run(
        "session-1",
        events=(
            RecordedEvent(frame=1, event_type="INPUT", data={"key": "a"}),
            RecordedEvent(frame=2, event_type="DAMAGE", data={"value": 10}),
            RecordedEvent(frame=3, event_type="INPUT", data={"key": "b"}),
        ),
    )
    app = create_app(application_facade(results=(run,)))

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/results/session-1/events",
            params={"offset": 1, "limit": 1, "event_type": "INPUT"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["offset"] == 1
    assert body["limit"] == 1
    assert body["total"] == 2
    assert [item["frame"] for item in body["items"]] == [3]


def test_results_missing_run_returns_not_found(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.get("/api/v1/results/missing-session")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_results_list_filters_by_name_state_and_time(application_facade) -> None:
    app = create_app(
        application_facade(
            results=(
                _run_at(
                    "session-1",
                    name="主配队",
                    created_at="2026-08-17T12:00:00+00:00",
                ),
                _run_at(
                    "session-2",
                    name="测试",
                    created_at="2026-08-18T12:00:00+00:00",
                ),
                _run_at(
                    "session-3",
                    name="主配队",
                    state="failed",
                    created_at="2026-08-19T12:00:00+00:00",
                ),
            )
        )
    )

    with TestClient(app) as client:
        by_name = client.get("/api/v1/results", params={"q": "主配"})
        by_name_and_state = client.get(
            "/api/v1/results",
            params={"q": "主配", "state": "completed"},
        )
        by_time = client.get(
            "/api/v1/results",
            params={
                "created_from": "2026-08-18T00:00:00+00:00",
                "created_to": "2026-08-19T23:59:59+00:00",
            },
        )

    assert [item["session_id"] for item in by_name.json()["items"]] == [
        "session-3",
        "session-1",
    ]
    assert [item["session_id"] for item in by_name_and_state.json()["items"]] == ["session-1"]
    assert [item["session_id"] for item in by_time.json()["items"]] == [
        "session-3",
        "session-2",
    ]


def test_results_list_ids_mode_ignores_other_filters_and_preserves_order(
    application_facade,
) -> None:
    app = create_app(
        application_facade(
            results=(
                _run_at(
                    "session-1",
                    name="主配队",
                    created_at="2026-08-17T12:00:00+00:00",
                ),
                _run_at(
                    "session-3",
                    name="主配队",
                    state="failed",
                    created_at="2026-08-19T12:00:00+00:00",
                ),
            )
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/results",
            params={"ids": "session-3,session-1,missing", "state": "failed"},
        )

    assert [item["session_id"] for item in response.json()["items"]] == [
        "session-3",
        "session-1",
    ]


def test_results_list_ids_rejects_more_than_200(application_facade) -> None:
    app = create_app(application_facade())
    ids = ",".join(f"session-{index}" for index in range(201))

    with TestClient(app) as client:
        response = client.get("/api/v1/results", params={"ids": ids})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_failed"


def test_results_event_detail_normalizes_damage_view(application_facade) -> None:
    run = _run(
        "session-1",
        events=(
            RecordedEvent(
                ordinal=0,
                frame=1,
                event_type="SIMULATION_STARTED",
                data={"ok": True},
            ),
            RecordedEvent(
                ordinal=1,
                frame=120,
                event_type="DAMAGE_RESOLVED",
                data={
                    "result": {
                        "request_id": "damage:1",
                        "final_damage": 2025.0,
                    },
                    "audit": {
                        "component_results": [],
                        "critical": {"outcome": "critical", "multiplier": 2.5},
                    },
                },
            ),
        ),
    )
    app = create_app(application_facade(results=(run,)))

    with TestClient(app) as client:
        listed = client.get("/api/v1/results/session-1/events")
        damage_detail = client.get("/api/v1/results/session-1/events/1")
        plain_detail = client.get("/api/v1/results/session-1/events/0")
        missing = client.get("/api/v1/results/session-1/events/9")

    assert listed.status_code == 200
    assert [item["ordinal"] for item in listed.json()["items"]] == [0, 1]

    assert damage_detail.status_code == 200
    body = damage_detail.json()
    assert body["ordinal"] == 1
    assert body["frame"] == 120
    assert body["damage"]["summary"]["request_id"] == "damage:1"
    assert body["damage"]["audit"]["critical"]["outcome"] == "critical"

    assert plain_detail.status_code == 200
    assert plain_detail.json()["damage"] is None

    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"


def test_results_event_detail_missing_session_returns_not_found(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.get("/api/v1/results/missing-session/events/0")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_results_frame_state_returns_projection(application_facade) -> None:
    run = _run("session-1")
    run_details = RunDetail(
        session_id="session-2",
        state="completed",
        input_snapshot={"meta": {"name": "帧状态"}},
        initial_snapshot=_frame_snapshot(),
        summary=SimulationRunSummary(
            stop_reason="INPUT_EXHAUSTED",
            end_frame=600,
            frames_run=600,
        ),
        events=(
            RecordedEvent(
                ordinal=0,
                frame=30,
                event_type="CHARACTER_HEALTH_CHANGED",
                data={
                    "result": {
                        "target_ref": {
                            "kind": "character",
                            "entity_id": "character:slot_1",
                        },
                        "hp_before": 12000.0,
                        "hp_after": 7500.0,
                        "max_hp": 15000.0,
                    }
                },
            ),
        ),
        error_code=None,
        error_message=None,
        created_at="2026-08-17T12:00:00+00:00",
        started_at=None,
        finished_at=None,
    )
    app = create_app(application_facade(results=(run, run_details)))

    with TestClient(app) as client:
        response = client.get("/api/v1/results/session-2/frames/30")
        out_of_range = client.get("/api/v1/results/session-2/frames/601")
        negative = client.get("/api/v1/results/session-2/frames/-1")
        missing_session = client.get("/api/v1/results/missing-session/frames/1")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-2"
    assert body["frame"] == 30
    assert body["time_seconds"] == 0.5
    assert body["team"]["active_slot"] == 1
    assert body["coverage"]["team"] == "folded"
    assert body["coverage"]["aura"] == "baseline_only"
    character = body["characters"][0]
    assert character["health"] == {
        "current_hp": 7500.0,
        "max_hp": 15000.0,
        "hp_ratio": 0.5,
    }
    assert character["active"] is True

    assert out_of_range.status_code == 404
    assert out_of_range.json()["code"] == "frame_out_of_range"
    assert negative.status_code == 404
    assert negative.json()["code"] == "frame_out_of_range"
    assert missing_session.status_code == 404
    assert missing_session.json()["code"] == "not_found"


def _frame_snapshot() -> dict[str, object]:
    return {
        "frame": 0,
        "providers": {
            "team": {
                "frame": 0,
                "active_slot": 1,
                "characters": [
                    {
                        "slot": 1,
                        "character_key": "character:test_a",
                        "combat_entity_id": "character:slot_1",
                        "current_hp": 12000.0,
                        "current_energy": 0.0,
                    }
                ],
            },
            "attributes": {
                "frame": 0,
                "subjects": {
                    "character:slot_1": {
                        "stat.hp.max": {"value": 15000.0, "applied_terms": []},
                    }
                },
            },
            "resonance": {"active_keys": ()},
            "moonsign": {"level": "", "moonsign_character_refs": ()},
            "buff": {"frame": 0, "instances": []},
        },
    }
