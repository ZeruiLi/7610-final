from __future__ import annotations

from typing import List, Optional

from services.session import Turn, session_manager


def fetch_history(session_id: Optional[str]) -> List[Turn]:
    """Return history for a session or an empty list if session_id is falsy."""
    if not session_id:
        return []
    return session_manager.get_history(session_id)


def record_turn(session_id: Optional[str], user_query: str, system_response: str) -> None:
    """Persist a user/assistant exchange if a session is supplied."""
    if not session_id:
        return
    session_manager.add_turn(session_id, user_query, system_response)


def reset_session(session_id: Optional[str]) -> None:
    """Clear memory for a session id."""
    if not session_id:
        return
    session_manager.reset(session_id)
