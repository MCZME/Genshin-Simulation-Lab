"""结果查询 HTTP 路由单元测试。"""

from fastapi.testclient import TestClient

from genshin_sim.analysis.processors.metrics import DamageMetrics, MetricValue
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


def _metrics(session_id: str) -> DamageMetrics:
    return DamageMetrics(
        frames_run=600,
        frames_per_second=60,
        total_damage=MetricValue("total_damage", 1200.0, "total"),
        dps=MetricValue("dps", 120.0, "dps"),
        highest_hit=MetricValue("highest_hit", 800.0, "max"),
        average_hit=MetricValue("average_hit", 600.0, "avg"),
        damage_share_by_source=(),
        damage_share_by_kind=(),
        total_healing=MetricValue("total_healing", 0.0, "heal"),
        healing_share_by_source=(),
    )


def test_results_list_and_detail_hide_sensitive_fields(application_facade) -> None:
    events = (
        RecordedEvent(frame=1, event_type="DAMAGE_DEALT", data={"value": 1}),
        RecordedEvent(frame=2, event_type="DAMAGE_DEALT", data={"value": 2}),
    )
    run = _run("session-1", events=events)
    app = create_app(
        application_facade(
            results=(run,),
            metrics={"session-1": _metrics("session-1")},
        )
    )

    with TestClient(app) as client:
        listed = client.get("/api/v1/results")
        detail = client.get("/api/v1/results/session-1")
        metrics = client.get("/api/v1/results/session-1/metrics")

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

    assert metrics.status_code == 200
    assert metrics.json()["total_damage"]["value"] == 1200.0
    assert metrics.json()["dps"]["value"] == 120.0


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


def test_results_metrics_unavailable_returns_conflict(application_facade) -> None:
    app = create_app(application_facade(results=(_run("session-failed", state="failed"),)))

    with TestClient(app) as client:
        response = client.get("/api/v1/results/session-failed/metrics")

    assert response.status_code == 409
    assert response.json()["code"] == "metrics_unavailable"


def test_results_missing_run_returns_not_found(application_facade) -> None:
    app = create_app(application_facade())

    with TestClient(app) as client:
        response = client.get("/api/v1/results/missing-session")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
