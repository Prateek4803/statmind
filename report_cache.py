"""
StatMind — Bounded Report Cache  (P0-SEC-2)

Extracted from main.py so it can be:
  - Unit tested without importing the full FastAPI app
  - Reused from any router module

Usage in main.py:
    from report_cache import ReportCache
    _report_cache = ReportCache()
    _report_cache.set(report_id, path)
    path = _report_cache.get(report_id)   # None if expired / not found
"""

import os
import time
import threading


class ReportCache:
    """
    Thread-safe in-memory report cache with TTL eviction and size cap.

    Replaces the previous unbounded dict `_report_cache: dict = {}` which
    accumulated file paths indefinitely on a long-running server.

    Features:
      - Per-entry TTL (default 3600s / 1 hour)
      - Hard cap on entry count (default 200); evicts oldest when full
      - Automatic deletion of temp PDF files on expiry
      - Background cleanup thread (runs every 5 minutes, daemon)
      - Thread-safe via threading.Lock
    """

    def __init__(self, ttl: int = 3600, maxsize: int = 200):
        self._store: dict[str, tuple[str, float]] = {}  # id → (path, expires_at)
        self._lock    = threading.Lock()
        self._ttl     = ttl
        self._max     = maxsize
        self._start_cleanup()

    # ── Public API ─────────────────────────────────────────────────────────────

    def set(self, report_id: str, path: str) -> None:
        with self._lock:
            self._evict_expired()
            if len(self._store) >= self._max:
                self._evict_oldest()
            self._store[report_id] = (path, time.monotonic() + self._ttl)

    def get(self, report_id: str) -> str | None:
        with self._lock:
            entry = self._store.get(report_id)
            if entry is None:
                return None
            path, expires_at = entry
            if time.monotonic() > expires_at:
                self._delete_entry(report_id)
                return None
            return path

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _evict_expired(self) -> None:
        now     = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            self._delete_entry(k)

    def _evict_oldest(self) -> None:
        if not self._store:
            return
        oldest_id = min(self._store.items(), key=lambda kv: kv[1][1])[0]
        self._delete_entry(oldest_id)

    def _delete_entry(self, report_id: str) -> None:
        entry = self._store.pop(report_id, None)
        if entry:
            path = entry[0]
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    def _start_cleanup(self) -> None:
        def _loop():
            while True:
                time.sleep(300)
                try:
                    with self._lock:
                        self._evict_expired()
                except Exception:
                    pass
        threading.Thread(target=_loop, daemon=True).start()
