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

    def add_turn(self, session_id: str, user_query: str, system_response: str) -> None:
        if not session_id:
            return
        
        self._cleanup()
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        
        now = time.time()
        self._sessions[session_id].append({"role": "user", "content": user_query, "timestamp": now})
        self._sessions[session_id].append({"role": "assistant", "content": system_response, "timestamp": now})
        
        # Trim history
        if len(self._sessions[session_id]) > self.max_history * 2:
             self._sessions[session_id] = self._sessions[session_id][-(self.max_history * 2):]
        
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
