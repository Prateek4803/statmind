"""
StatMind — 8D Problem Solving Engine
Creates, updates, and retrieves 8D reports.
"""

import uuid, datetime

_store: dict = {}   # {report_id: report_dict}


def _new_report(data: dict) -> dict:
    return {
        "report_id":   str(uuid.uuid4())[:8].upper(),
        "created_at":  datetime.datetime.utcnow().isoformat() + "Z",
        "status":      "Open",
        "team":        data.get("team", []),
        "problem":     data.get("problem", ""),
        "d3_containment":  data.get("d3_containment", ""),
        "d4_root_cause":   data.get("d4_root_cause", ""),
        "d5_corrections":  data.get("d5_corrections", []),
        "d6_implemented":  data.get("d6_implemented", ""),
        "d7_prevention":   data.get("d7_prevention", ""),
        "d8_recognition":  data.get("d8_recognition", ""),
    }


def report_to_dict(report: dict) -> dict:
    return report


def create_8d(data: dict) -> dict:
    r = _new_report(data)
    _store[r["report_id"]] = r
    return r


def update_8d(report_id: str, updates: dict) -> dict:
    if report_id not in _store:
        raise ValueError(f"8D report '{report_id}' not found")
    _store[report_id].update(updates)
    _store[report_id]["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    return _store[report_id]


def get_8d(report_id: str) -> dict:
    if report_id not in _store:
        raise ValueError(f"8D report '{report_id}' not found")
    return _store[report_id]


def list_8d() -> list:
    return list(_store.values())


def delete_8d(report_id: str) -> bool:
    return bool(_store.pop(report_id, None))
