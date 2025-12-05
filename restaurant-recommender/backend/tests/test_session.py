from __future__ import annotations

import time

from services.session import SessionManager


def test_add_turn_pairs_and_trim() -> None:
    mgr = SessionManager(max_history=2, ttl_sec=1000)
    for idx in range(3):
        mgr.add_turn("sess-1", f"user-{idx}", f"assistant-{idx}")

    history = mgr.get_history("sess-1")
    assert len(history) == 4  # max_history * 2
    assert history[0]["content"] == "user-1"
    assert history[-1]["content"] == "assistant-2"


def test_reset_clears_state() -> None:
    mgr = SessionManager(max_history=2, ttl_sec=1000)
    mgr.add_user_turn("sess-2", "hello")
    mgr.add_assistant_turn("sess-2", "world")
    assert mgr.get_history("sess-2")

    mgr.reset("sess-2")
    assert mgr.get_history("sess-2") == []


def test_cleanup_by_ttl() -> None:
    mgr = SessionManager(max_history=2, ttl_sec=1)
    mgr.add_turn("sess-ttl", "hi", "there")
    assert "sess-ttl" in mgr._sessions  # type: ignore[attr-defined]

    # force timestamp to be stale
    mgr._last_access["sess-ttl"] = time.time() - 10  # type: ignore[attr-defined]
    history = mgr.get_history("sess-ttl")
    assert history == []
    assert "sess-ttl" not in mgr._sessions  # type: ignore[attr-defined]
