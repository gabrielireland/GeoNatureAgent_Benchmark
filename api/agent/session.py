"""Thread-safe in-memory session store for conversation history.

Includes:
- TTL-based expiry (30 min default)
- Max concurrent session count with LRU eviction
- Message trimming to keep only the last N user turns
"""

import threading
import time
from typing import Any, Dict, List, Optional

SESSION_TTL = 1800  # 30 minutes
SESSION_MAX_TURNS = 8  # max user-initiated turns to keep
SESSION_MAX_COUNT = 500  # max concurrent sessions in memory


class SessionStore:
    """Thread-safe in-memory store for conversation history keyed by session_id."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _cleanup(self):
        """Remove sessions inactive for > SESSION_TTL and enforce max count."""
        now = time.time()
        expired = [
            sid for sid, data in self._sessions.items()
            if now - data["last_access"] > SESSION_TTL
        ]
        for sid in expired:
            del self._sessions[sid]
        # If still over limit, evict oldest sessions
        if len(self._sessions) > SESSION_MAX_COUNT:
            sorted_sessions = sorted(
                self._sessions.items(), key=lambda x: x[1]["last_access"]
            )
            to_evict = len(self._sessions) - SESSION_MAX_COUNT
            for sid, _ in sorted_sessions[:to_evict]:
                del self._sessions[sid]

    def get_messages(self, session_id: Optional[str]) -> List[Dict]:
        if not session_id:
            return []
        with self._lock:
            self._cleanup()
            session = self._sessions.get(session_id)
            if not session:
                return []
            session["last_access"] = time.time()
            return list(session["messages"])

    def save_messages(self, session_id: Optional[str], messages: List[Dict]):
        if not session_id:
            return
        trimmed = self._trim_messages(messages)
        with self._lock:
            self._cleanup()
            self._sessions[session_id] = {
                "messages": trimmed,
                "last_access": time.time(),
            }

    @staticmethod
    def _trim_messages(messages: List[Dict]) -> List[Dict]:
        """Keep only the last SESSION_MAX_TURNS user-initiated turns.

        A 'user turn' is a message with role=user whose content is a string
        (not a list of tool_results). We count backwards and keep everything
        from the Nth user turn onward.
        """
        user_turn_indices = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                user_turn_indices.append(i)

        if len(user_turn_indices) <= SESSION_MAX_TURNS:
            return messages

        cut_from = user_turn_indices[-SESSION_MAX_TURNS]
        return messages[cut_from:]


# Module-level singleton — used by agent.py and benchmark runner
session_store = SessionStore()
