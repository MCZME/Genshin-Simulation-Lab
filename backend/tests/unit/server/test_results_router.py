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
    assert [item["session_id"] for item in by_name_and_state.json()["items"]] == [
        "session-1"
    ]
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
