from __future__ import annotations

from typing import cast

from genshin_sim.application.execution.models import RecordedEvent
from genshin_sim.application.models import RunDetail
from genshin_sim.application.services import (
    ResultDatabaseService,
    ResultsService,
)
from genshin_sim.application.services.protocols import ResultRepository


def test_result_database_service_delegates_initialization(tmp_path):
    calls: list[str] = []

    def init_database(path):
        calls.append(str(path))
        return path

    db_path = tmp_path / "results.db"
    service = ResultDatabaseService(init_database)

    assert service.init_database(db_path) == db_path
    assert calls == [str(db_path)]


class _FakeResultRepository:
    def __init__(self, run: RunDetail) -> None:
        self._run = run

    def get_run(self, session_id: str, *, include_events: bool = True) -> RunDetail:
        assert session_id == "run:1"
        return self._run

    def list_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        state: str | None = None,
    ) -> tuple[object, ...]:
        return ()

    def get_events(self, session_id: str, **kwargs: object) -> tuple[RecordedEvent, ...]:
        events = self._run.events
        frame_min = cast(int | None, kwargs.get("frame_min"))
        frame_max = cast(int | None, kwargs.get("frame_max"))
        event_type = cast(str | None, kwargs.get("event_type"))
        if frame_min is not None:
            events = tuple(event for event in events if event.frame >= frame_min)
        if frame_max is not None:
            events = tuple(event for event in events if event.frame <= frame_max)
        if event_type is not None:
            events = tuple(event for event in events if event.event_type == event_type)
        offset = cast(int, kwargs.get("offset") or 0)
        limit = cast(int | None, kwargs.get("limit"))
        end = None if limit is None else offset + limit
        return events[offset:end]

    def count_events(self, session_id: str, **kwargs: object) -> int:
        return len(self.get_events(session_id, **kwargs))


def test_results_service_counts_filtered_events():
    run = RunDetail(
        session_id="run:1",
        state="completed",
        input_snapshot={},
        initial_snapshot=None,
        summary=None,
        events=(
            RecordedEvent(frame=1, event_type="INPUT", data={}),
            RecordedEvent(frame=2, event_type="DAMAGE_RESOLVED", data={}),
        ),
        error_code=None,
        error_message=None,
        created_at="2026-08-11T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )
    service = ResultsService(cast(ResultRepository, _FakeResultRepository(run)))

    count = service.count_events("run:1", frame_min=2, event_type="DAMAGE_RESOLVED")

    assert count == 1
