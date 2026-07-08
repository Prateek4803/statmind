"""Session 6: /api/v1/health must expose the baked release SHA so deploys can
verify the NEW code is serving (not just any 200)."""
import importlib
import os

from fastapi.testclient import TestClient


def test_health_reports_release_sha(monkeypatch):
    monkeypatch.setenv("RELEASE_SHA", "abc123deadbeef")
    import main
    importlib.reload_health = None  # payload reads env at call time — no reload needed
    r = TestClient(main.app).get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["release"] == "abc123deadbeef"
    assert body["status"] == "ok"


def test_health_release_defaults_to_unknown(monkeypatch):
    monkeypatch.delenv("RELEASE_SHA", raising=False)
    import main
    r = TestClient(main.app).get("/api/v1/health")
    assert r.json()["release"] == "unknown"
