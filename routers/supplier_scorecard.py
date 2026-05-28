"""
StatMind — Supplier Quality Scorecard
Create, update, and rank supplier quality KPI scorecards.
"""

import uuid, datetime

_store: dict = {}   # {scorecard_id: scorecard}


def _new_scorecard(data: dict) -> dict:
    return {
        "scorecard_id": str(uuid.uuid4())[:8].upper(),
        "supplier_name": data.get("supplier_name", "Unknown"),
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "kpis": {
            "on_time_delivery_pct":    data.get("on_time_delivery_pct", 0),
            "defect_rate_ppm":         data.get("defect_rate_ppm", 0),
            "cpk_min":                 data.get("cpk_min", 0),
            "audit_score":             data.get("audit_score", 0),
            "corrective_action_rate":  data.get("corrective_action_rate", 0),
        },
        "audits": [],
        "overall_score": 0,
        "rating": "Not rated",
    }


def _compute_score(sc: dict) -> dict:
    k = sc["kpis"]
    # Simple weighted score: delivery 30%, defect 30%, Cpk 20%, audit 20%
    d   = min(k["on_time_delivery_pct"], 100) / 100
    ppm = max(0, 1 - k["defect_rate_ppm"] / 10000)
    cpk = min(k["cpk_min"] / 1.67, 1.0)
    aud = min(k["audit_score"], 100) / 100
    score = round((d*0.3 + ppm*0.3 + cpk*0.2 + aud*0.2) * 100, 1)
    rating = ("Preferred" if score >= 85 else
              "Approved"  if score >= 70 else
              "Conditional" if score >= 55 else "Disqualified")
    sc["overall_score"] = score
    sc["rating"] = rating
    return sc


def scorecard_to_dict(sc: dict) -> dict:
    return sc


def create_scorecard(data: dict) -> dict:
    sc = _compute_score(_new_scorecard(data))
    _store[sc["scorecard_id"]] = sc
    return sc


def update_kpis(scorecard_id: str, kpis: dict) -> dict:
    if scorecard_id not in _store:
        raise ValueError(f"Scorecard '{scorecard_id}' not found")
    _store[scorecard_id]["kpis"].update(kpis)
    return _compute_score(_store[scorecard_id])


def add_audit(scorecard_id: str, audit: dict) -> dict:
    if scorecard_id not in _store:
        raise ValueError(f"Scorecard '{scorecard_id}' not found")
    audit["date"] = datetime.datetime.utcnow().isoformat() + "Z"
    _store[scorecard_id]["audits"].append(audit)
    if "score" in audit:
        _store[scorecard_id]["kpis"]["audit_score"] = audit["score"]
        _compute_score(_store[scorecard_id])
    return _store[scorecard_id]


def get_scorecard(scorecard_id: str) -> dict:
    if scorecard_id not in _store:
        raise ValueError(f"Scorecard '{scorecard_id}' not found")
    return _store[scorecard_id]


def list_scorecards() -> list:
    return list(_store.values())


def rank_suppliers() -> list:
    return sorted(_store.values(), key=lambda x: x["overall_score"], reverse=True)
