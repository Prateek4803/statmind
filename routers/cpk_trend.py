"""
StatMind — Cpk Trend Tracking
Stores and retrieves historical capability studies per parameter.
In-memory store (persists for Railway session lifetime).
"""

import datetime

_store: dict = {}   # {parameter: [study, ...]}


def add_cpk_study(parameter: str, cpk: float, cp: float, ppk: float,
                  n: int, usl: float, lsl: float,
                  lot_id: str = None, tool_id: str = None) -> dict:
    study = {
        "parameter": parameter,
        "cpk": round(cpk, 4),
        "cp":  round(cp,  4),
        "ppk": round(ppk, 4),
        "n":   n,
        "usl": usl, "lsl": lsl,
        "lot_id":  lot_id,
        "tool_id": tool_id,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    _store.setdefault(parameter, []).append(study)
    return study


def get_cpk_trend(parameter: str) -> list:
    return _store.get(parameter, [])


def list_parameters() -> list:
    return [
        {"parameter": p, "n_studies": len(v),
         "latest_cpk": v[-1]["cpk"] if v else None}
        for p, v in _store.items()
    ]
