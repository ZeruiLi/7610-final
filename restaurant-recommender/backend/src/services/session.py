from __future__ import annotations

import time
from typing import Dict, List, Optional, TypedDict


class Turn(TypedDict):
    role: str  # "user" or "assistant"
    content: str
    timestamp: float


class SessionManager:
    """Simple in-memory session manager."""

    def __init__(self, max_history: int = 10, ttl_sec: int = 3600) -> None:
        self._sessions: Dict[str, List[Turn]] = {}
        self._last_access: Dict[str, float] = {}
        self.max_history = max_history
        self.ttl_sec = ttl_sec

    def get_history(self, session_id: str) -> List[Turn]:
        self._cleanup()
        if not session_id:
            return []
        self._last_access[session_id] = time.time()
        return self._sessions.get(session_id, [])

    def add_user_turn(self, session_id: str, user_query: str) -> None:
        self._append_turn(session_id, "user", user_query)

    def add_assistant_turn(self, session_id: str, response: str) -> None:
        self._append_turn(session_id, "assistant", response)

    def add_turn(self, session_id: str, user_query: str, system_response: str) -> None:
        """Append user + assistant messages as a pair for backward compatibility."""
        if not session_id:
            return
        self._append_turn(session_id, "user", user_query)
        self._append_turn(session_id, "assistant", system_response)

    def reset(self, session_id: str) -> None:
        """Clear a session's history."""
        if not session_id:
            return
        self._sessions.pop(session_id, None)
        self._last_access.pop(session_id, None)

    def _append_turn(self, session_id: str, role: str, content: str) -> None:
        if not session_id:
            return

        self._cleanup()
        now = time.time()
        history = self._sessions.setdefault(session_id, [])
        history.append({"role": role, "content": content, "timestamp": now})

        max_len = self.max_history * 2
        if len(history) > max_len:
            self._sessions[session_id] = history[-max_len:]

        self._last_access[session_id] = now

    def _cleanup(self) -> None:
        """Remove expired sessions."""
        now = time.time()
        expired = [
            sid for sid, last in self._last_access.items() 
            if now - last > self.ttl_sec
        ]
        for sid in expired:
            del self._sessions[sid]
            del self._last_access[sid]

# Global singleton
session_manager = SessionManager()
