"""
multistage_data.py — Generator for multistage manufacturing datasets with
KNOWN causal ground truth.

Motivation (Prof. Paynabar feedback, 2026-07): real production is a *dependent
cascade*. A change at stage 1 does not surface at stage 1 — it propagates to
stage 3, or stages 7-8, with a delay (lag) and attenuation. Monitoring each
stage in isolation (what StatMind does today) misses this structure. A serious
tool must trace a downstream alarm to its true upstream origin.

This module builds datasets where that structure is DESIGNED and RECORDED, so
the multistage analysis engine (Session M2) can be tested against known truth:
"given a stage-7 excursion, does the engine attribute it to stage 1 at the
correct lag?"

── Model ──────────────────────────────────────────────────────────────────────
A line of K stages processes `n_units` units in sequence (unit_id 1..n). Each
unit carries a quality characteristic measured at every stage. Stage k's value
is:

    x[k, u] = base[k]
              + Σ_j  coupling[j→k] * (x[j, u - lag[j→k]] - base[j])   # upstream propagation
              + drift[k, u]                                            # optional per-stage drift
              + fault_contribution[k, u]                              # injected faults, propagated
              + noise[k, u]

Faults are injected at a SOURCE stage over a unit range; each fault propagates
downstream along the coupling graph, arriving at stage k with the summed lag of
the path and multiplied by the product of couplings (attenuation). The full
propagation is recorded in `ground_truth` so tests can assert origin + lag.

Coupling graph default (a realistic-ish semiconductor-like flow, chain with a
couple of skip links so stage 1 reaches stages 3 AND 7-8, matching the
professor's exact example):

    1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
    1 ┄┄┄┄→ 3            (skip: stage-1 change shows at stage 3)
    3 ┄┄┄┄┄┄┄┄┄┄┄→ 7     (skip: carries a stage-1 disturbance out to 7-8)
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
import pandas as pd


# ── Ground-truth records ──────────────────────────────────────────────────────
@dataclass
class PropagationLink:
    """One causal edge in the propagation of a fault, for test assertions."""
    from_stage: int
    to_stage: int
    lag: int              # units of delay between from_stage and to_stage
    gain: float           # multiplicative attenuation along this edge


@dataclass
class InjectedFault:
    """A fault injected at a source stage, with its full downstream footprint."""
    source_stage: int
    unit_start: int
    unit_end: int
    magnitude: float          # in stage-1 sigma units
    kind: str                 # 'step' | 'drift'
    # cumulative arrival at each affected downstream stage: {stage: (lag, gain)}
    downstream_arrivals: dict = field(default_factory=dict)


@dataclass
class MultistageGroundTruth:
    n_stages: int
    n_units: int
    stage_names: list
    coupling_edges: list           # list[PropagationLink] — the static graph
    faults: list                   # list[InjectedFault]
    base_means: list
    base_sigmas: list

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ── Generator ─────────────────────────────────────────────────────────────────
_DEFAULT_STAGE_NAMES = [
    "S1_Incoming", "S2_Clean", "S3_Deposition", "S4_Litho",
    "S5_Etch", "S6_Implant", "S7_Anneal", "S8_Final_CD",
]

# coupling graph: (from, to, lag_units, gain). 1-indexed stages.
_DEFAULT_EDGES = [
    (1, 2, 1, 0.55), (2, 3, 1, 0.55), (3, 4, 1, 0.50), (4, 5, 1, 0.55),
    (5, 6, 1, 0.50), (6, 7, 1, 0.55), (7, 8, 1, 0.60),
    (1, 3, 2, 0.35),          # skip link: stage-1 disturbance also reaches stage 3 directly
    (3, 7, 3, 0.40),          # skip link: carries disturbances from the front of the line to 7-8
]


def generate_multistage_dataset(
    n_units: int = 300,
    n_stages: int = 8,
    stage_names: Optional[list] = None,
    coupling_edges: Optional[list] = None,
    faults: Optional[list] = None,
    base_mean: float = 100.0,
    base_sigma: float = 2.0,
    seed: int = 2026,
) -> tuple[pd.DataFrame, MultistageGroundTruth]:
    """
    Returns (long_df, ground_truth).

    long_df columns: unit_id, stage_index (1..K), stage_name, value, timestamp.
    Long format is the canonical multistage schema (one row per unit×stage);
    a wide pivot is available via `to_wide(df)`.

    `faults`: list of dicts, each {source_stage, unit_start, unit_end,
    magnitude (in stage sigma), kind ('step'|'drift')}. If None, a default
    stage-1 step fault is injected so the classic "upstream cause, downstream
    alarm" story is present out of the box.
    """
    rng = np.random.default_rng(seed)
    names = stage_names or _DEFAULT_STAGE_NAMES[:n_stages]
    if len(names) < n_stages:
        names = names + [f"S{i+1}" for i in range(len(names), n_stages)]
    edges_raw = coupling_edges or [e for e in _DEFAULT_EDGES if e[0] <= n_stages and e[1] <= n_stages]

    base_means = [base_mean + i * 0.0 for i in range(n_stages)]
    base_sigmas = [base_sigma for _ in range(n_stages)]

    # Default fault: a stage-1 step shift over units 150..300 (second half),
    # magnitude 3 sigma — must surface downstream at stages 3 and 7-8.
    if faults is None:
        faults = [{"source_stage": 1, "unit_start": 150, "unit_end": n_units,
                   "magnitude": 3.0, "kind": "step"}]

    # Independent innovation for each stage/unit
    innov = {k: rng.normal(0, base_sigmas[k - 1], n_units + 8) for k in range(1, n_stages + 1)}

    # Build per-stage disturbance from injected faults at their SOURCE stage
    # (in that stage's own units, pre-propagation).
    source_disturbance = {k: np.zeros(n_units + 8) for k in range(1, n_stages + 1)}
    injected: list[InjectedFault] = []
    for f in faults:
        src = int(f["source_stage"])
        u0, u1 = int(f["unit_start"]), int(f["unit_end"])
        mag = float(f["magnitude"]) * base_sigmas[src - 1]
        kind = f.get("kind", "step")
        arr = np.zeros(n_units + 8)
        idx = np.arange(n_units + 8)
        mask = (idx >= u0 - 1) & (idx < u1)
        if kind == "step":
            arr[mask] = mag
        elif kind == "drift":
            span = max(1, u1 - u0)
            arr[mask] = mag * (idx[mask] - (u0 - 1)) / span
        else:
            raise ValueError(f"Unknown fault kind: {kind}")
        source_disturbance[src] += arr
        injected.append(InjectedFault(source_stage=src, unit_start=u0, unit_end=u1,
                                      magnitude=float(f["magnitude"]), kind=kind))

    # Compute stage values in topological order (stage index order works for a
    # forward DAG). x[k] depends on upstream x[j] at lag, plus own innovation and
    # own source disturbance.
    edges = [PropagationLink(int(a), int(b), int(l), float(g)) for (a, b, l, g) in edges_raw]
    incoming = {k: [e for e in edges if e.to_stage == k] for k in range(1, n_stages + 1)}
    x = {k: np.zeros(n_units + 8) for k in range(1, n_stages + 1)}

    for k in range(1, n_stages + 1):
        val = base_means[k - 1] + innov[k] + source_disturbance[k]
        for e in incoming[k]:
            up = x[e.from_stage]
            lagged = np.zeros_like(up)
            if e.lag > 0:
                lagged[e.lag:] = up[:-e.lag]
            else:
                lagged = up.copy()
            # propagate the DEVIATION of the upstream stage from its base
            val += e.gain * (lagged - base_means[e.from_stage - 1])
        x[k] = val

    # Trim the 8-unit warmup padding
    for k in x:
        x[k] = x[k][:n_units]

    # Record each fault's downstream arrivals by walking the coupling DAG from
    # the source, summing lag and multiplying gain along each path (max-gain path
    # recorded per reachable stage — that's the dominant propagation route).
    def _best_paths(src: int):
        # Dijkstra-ish over gain (maximize product of gains), tracking summed lag.
        best = {src: (0, 1.0)}  # stage -> (lag, gain)
        frontier = [src]
        # simple relaxation over the DAG (few nodes)
        changed = True
        while changed:
            changed = False
            for e in edges:
                if e.from_stage in best:
                    lag0, gain0 = best[e.from_stage]
                    cand = (lag0 + e.lag, gain0 * e.gain)
                    if e.to_stage not in best or cand[1] > best[e.to_stage][1]:
                        best[e.to_stage] = cand
                        changed = True
        best.pop(src, None)
        return best

    for fault in injected:
        fault.downstream_arrivals = {
            stage: {"lag": lag, "gain": round(gain, 4)}
            for stage, (lag, gain) in _best_paths(fault.source_stage).items()
        }

    # Long-format dataframe
    rows = []
    t0 = pd.Timestamp("2026-01-01T00:00:00")
    for u in range(n_units):
        ts = t0 + pd.Timedelta(minutes=u)
        for k in range(1, n_stages + 1):
            rows.append({
                "unit_id": u + 1,
                "stage_index": k,
                "stage_name": names[k - 1],
                "value": round(float(x[k][u]), 4),
                "timestamp": ts.isoformat(),
            })
    long_df = pd.DataFrame(rows)

    gt = MultistageGroundTruth(
        n_stages=n_stages, n_units=n_units, stage_names=names,
        coupling_edges=[asdict(e) for e in edges],
        faults=[asdict(f) for f in injected],
        base_means=base_means, base_sigmas=base_sigmas,
    )
    return long_df, gt


def to_wide(long_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot the canonical long format to wide: one column per stage, one row
    per unit. Convenient for correlation analysis and for users who think in
    spreadsheets."""
    wide = long_df.pivot(index="unit_id", columns="stage_name", values="value")
    # preserve stage order
    order = (long_df.sort_values("stage_index")
             .drop_duplicates("stage_name")["stage_name"].tolist())
    wide = wide[order].reset_index()
    wide.columns.name = None
    return wide


if __name__ == "__main__":
    df, gt = generate_multistage_dataset()
    print(f"Generated {len(df)} rows, {gt.n_stages} stages × {gt.n_units} units")
    print("Faults:", gt.faults[0]["source_stage"], "→ arrivals:",
          gt.faults[0]["downstream_arrivals"])
