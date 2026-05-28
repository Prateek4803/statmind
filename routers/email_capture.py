"""
email_capture.py — StatMind email capture module
Stores emails before PDF download. Zero external dependencies.
Uses SQLite directly so it works even if the main DB isn't configured.
"""

import sqlite3
import re
import os
import logging
from datetime import datetime, timezone

# Store in same location as main DB, fallback to /tmp
_DB_PATH = os.getenv("EMAIL_DB_PATH", "/app/data/emails.db")

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_captures (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            email     TEXT NOT NULL,
            source    TEXT DEFAULT 'pdf_download',
            captured_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email ON email_captures(email)")
    conn.commit()
    return conn


def validate_email(email: str) -> bool:
    return bool(email and _EMAIL_RE.match(email.strip()) and len(email) <= 254)


def save_email(email: str, source: str = "pdf_download") -> dict:
    """
    Save an email. Returns {"saved": True} or {"saved": False, "reason": "..."}
    Silently deduplicates — same email twice is not an error.
    """
    email = email.strip().lower()

    if not validate_email(email):
        return {"saved": False, "reason": "invalid_email"}

    try:
        conn = _get_conn()
        # Check if already captured
        existing = conn.execute(
            "SELECT id FROM email_captures WHERE email = ?", (email,)
        ).fetchone()

        if existing:
            conn.close()
            return {"saved": True, "new": False}

        conn.execute(
            "INSERT INTO email_captures (email, source, captured_at) VALUES (?, ?, ?)",
            (email, source, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
        logging.info(f"Email captured: {email[:3]}***@{email.split('@')[1]}")
        return {"saved": True, "new": True}

    except Exception as e:
        logging.error(f"Email capture failed: {e}")
        return {"saved": False, "reason": "db_error"}


def get_all_emails() -> list[dict]:
    """Admin use only — returns all captured emails."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT email, source, captured_at FROM email_captures ORDER BY captured_at DESC"
        ).fetchall()
        conn.close()
        return [{"email": r[0], "source": r[1], "captured_at": r[2]} for r in rows]
    except Exception as e:
        logging.error(f"Failed to fetch emails: {e}")
        return []
