from __future__ import annotations

from .types import Session


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(
                session_id=session_id,
                state={"todos": []},
            )
        return self._sessions[session_id]

    def get(self, session_id: str) -> Session:
        return self._sessions[session_id]
