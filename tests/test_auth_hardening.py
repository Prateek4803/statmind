"""
Tests for auth hardening (P1-SEC-3/4):
  - RFC-lite email validation with length cap on /magic-link and /email-capture
  - Per-email pending-token throttle (max 3 unexpired unused magic links)
  - Email-capture dedup per (email, source)
  - Per-route rate limits declared on the shared limiter
  - Input-bound validation on analysis endpoints (alpha, subgroup_size)
"""
import io
import uuid

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main
import auth

client = TestClient(main.app)


def _unique_email():
    return f"test-{uuid.uuid4().hex[:12]}@example.com"


# ── Email validation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    "",
    "no-at-sign",
    "two@@example.com",
    "control\nchars@example.com",
    "spaces in local@example.com",
    "a@b",                     # no TLD
    ("x" * 250) + "@long.com", # over 254 chars
])
def test_magic_link_rejects_invalid_email(bad):
    r = client.post("/api/v1/auth/magic-link", json={"email": bad})
    assert r.status_code == 400


def test_email_capture_rejects_invalid_email():
    r = client.post("/api/v1/auth/email-capture", json={"email": "not-an-email"})
    assert r.status_code == 400


def test_magic_link_accepts_and_normalizes_valid_email():
    email = _unique_email().upper()
    r = client.post("/api/v1/auth/magic-link", json={"email": email})
    assert r.status_code == 200
    assert email.lower() in r.json()["message"]


# ── Per-email pending-token throttle ─────────────────────────────────────────

def test_pending_token_throttle():
    email = _unique_email()
    # First 3 requests succeed (throttle allows up to _MAX_PENDING_TOKENS)
    for _ in range(auth._MAX_PENDING_TOKENS):
        r = client.post("/api/v1/auth/magic-link", json={"email": email})
        assert r.status_code == 200
    # 4th is rejected with 429
    r = client.post("/api/v1/auth/magic-link", json={"email": email})
    assert r.status_code == 429


# ── Email capture dedup ───────────────────────────────────────────────────────

def test_email_capture_dedup():
    email = _unique_email()
    for _ in range(3):
        r = client.post(
            "/api/v1/auth/email-capture",
            json={"email": email, "source": "test-suite"},
        )
        assert r.status_code == 200

    db = auth.get_db()
    try:
        count = db.execute(
            "SELECT COUNT(*) FROM email_captures WHERE email = ?", (email,)
        ).fetchone()[0]
    finally:
        db.close()
    assert count == 1


def test_email_capture_caps_source_length():
    email = _unique_email()
    r = client.post(
        "/api/v1/auth/email-capture",
        json={"email": email, "source": "x" * 5000},
    )
    assert r.status_code == 200
    db = auth.get_db()
    try:
        row = db.execute(
            "SELECT source FROM email_captures WHERE email = ?", (email,)
        ).fetchone()
    finally:
        db.close()
    assert len(row["source"]) <= 64


# ── Per-route rate limits are declared ────────────────────────────────────────

def test_strict_limits_declared_on_auth_routes():
    """The decorators must be wired to the shared limiter, not a local one."""
    from rate_limit import limiter as shared
    assert main.app.state.limiter is shared


# ── Analysis input bounds ─────────────────────────────────────────────────────

def _csv_bytes():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"X": rng.normal(100, 5, 60)})
    return df.to_csv(index=False).encode()


@pytest.mark.parametrize("alpha", [0, -0.1, 1.0, 2.5])
def test_normality_rejects_out_of_range_alpha(alpha):
    r = client.post(
        f"/api/v1/normality/analyze?alpha={alpha}",
        files={"file": ("d.csv", io.BytesIO(_csv_bytes()), "text/csv")},
    )
    assert r.status_code == 422


@pytest.mark.parametrize("sg", [0, -1, 101])
def test_capability_rejects_invalid_subgroup_size(sg):
    r = client.post(
        f"/api/v1/capability/analyze?column=X&usl=115&lsl=85&subgroup_size={sg}",
        files={"file": ("d.csv", io.BytesIO(_csv_bytes()), "text/csv")},
    )
    assert r.status_code == 422


def test_estimate_sigma_within_rejects_zero_subgroup():
    """Engine-level guard: previously ZeroDivisionError → unhandled 500."""
    from capability import estimate_sigma_within
    with pytest.raises(ValueError):
        estimate_sigma_within(np.arange(20, dtype=float), subgroup_size=0)


# ── Security headers ──────────────────────────────────────────────────────────

def test_csp_header_present():
    r = client.get("/api/v1/health")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
