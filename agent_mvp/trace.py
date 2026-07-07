from __future__ import annotations

from collections import defaultdict
from typing import Any

from .types import TraceEvent


class InMemoryTraceLogger:
    def __init__(self) -> None:
        self._events: dict[str, list[TraceEvent]] = defaultdict(list)

    def record(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        turn_id: int = 0,
    ) -> None:
        self._events[session_id].append(
            TraceEvent(
                session_id=session_id,
                event_type=event_type,
                payload=payload,
                turn_id=turn_id,
            )
        )

    def list_events(self, session_id: str) -> list[TraceEvent]:
        return list(self._events.get(session_id, []))

    def list_event_types(self, session_id: str) -> list[str]:
        return [event.event_type for event in self.list_events(session_id)]
