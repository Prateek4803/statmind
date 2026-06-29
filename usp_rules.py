"""
StatMind — USP Compendial Acceptance Rules
==========================================

Pure evaluation functions for USP General Chapter numeric acceptance criteria.
These implement the published *general-chapter default* thresholds as staged
decision logic and return a structured verdict + cited rationale that the CAPA
layer can consume (an OOS result auto-opens a deviation/CAPA).

IMPORTANT — regulated-use caveat
--------------------------------
The thresholds here are the GENERAL-CHAPTER DEFAULTS. Individual product
monographs can and do override them (especially Q for dissolution and M/L1/L2
for uniformity). Every verdict returned therefore carries `defaults_used=True`
and a `verify_monograph` note. This module must never be presented as an
authoritative pass/fail for a specific product without monograph confirmation.

References
----------
USP <711>  Dissolution — Acceptance Table 1 (immediate-release), stages S1–S3.
USP <905>  Uniformity of Dosage Units — Acceptance Value, stages L1/L2.
USP <788>  Particulate Matter in Injections — Method 1 (light obscuration).
USP <789>  Particulate Matter in Ophthalmic Solutions.
(Verify current wording at https://www.usp.org/ before regulated use.)
"""

from dataclasses import dataclass, field
from typing import List, Optional
from statistics import mean, pstdev


_VERIFY = ("Default general-chapter thresholds used. Verify against the specific "
           "product monograph before any regulated disposition — monographs can override.")


@dataclass
class CompendialVerdict:
    chapter: str                 # e.g. "USP <711>"
    test: str                    # e.g. "Dissolution (Immediate-Release)"
    stage_reached: str           # e.g. "S1", "S2", "S3"
    passed: bool
    oos: bool                    # True => auto-open CAPA/deviation
    rationale: str
    detail: List[str] = field(default_factory=list)
    defaults_used: bool = True
    verify_monograph: str = _VERIFY
    standard_reference: str = ""
    capa_action: str = ""        # what the CAPA engine should do on OOS


# ── USP <711> Dissolution — Acceptance Table 1 (Immediate-Release) ───────────
def evaluate_dissolution(
    s1_results: List[float],
    Q: float,
    s2_results: Optional[List[float]] = None,
    s3_results: Optional[List[float]] = None,
) -> CompendialVerdict:
    """Stage-wise S1->S2->S3 evaluation of immediate-release dissolution.

    Args:
        s1_results: the 6 Stage-1 unit results, as % of label claim dissolved.
        Q:          the monograph Q value (% dissolved at the specified time).
                    REQUIRED — there is no safe default; pass the monograph value.
        s2_results: 6 additional units (Stage 2) — provide only if S1 fails.
        s3_results: 12 additional units (Stage 3) — provide only if S2 fails.

    Acceptance (Table 1):
        S1 (n=6):  every unit >= Q + 5%
        S2 (n=12): average >= Q AND no unit < Q - 15%
        S3 (n=24): average >= Q AND not more than 2 units < Q - 15%
                   AND no unit < Q - 25%
    """
    ref = "USP <711> Dissolution, Acceptance Table 1"
    if not s1_results or len(s1_results) < 6:
        raise ValueError("S1 requires 6 unit results.")

    # ── Stage 1 ──
    s1_min = min(s1_results)
    if s1_min >= Q + 5:
        return CompendialVerdict(
            chapter="USP <711>", test="Dissolution (Immediate-Release)",
            stage_reached="S1", passed=True, oos=False,
            rationale=f"S1 met: all 6 units >= Q+5% ({Q+5:.1f}%). Lowest unit {s1_min:.1f}%.",
            detail=[f"Q={Q:.1f}%", f"S1 acceptance = each unit >= {Q+5:.1f}%",
                    f"S1 min = {s1_min:.1f}%"],
            standard_reference=ref,
        )

    # S1 failed — need S2 data to continue
    if not s2_results:
        return CompendialVerdict(
            chapter="USP <711>", test="Dissolution (Immediate-Release)",
            stage_reached="S1", passed=False, oos=False,
            rationale=(f"S1 not met (lowest unit {s1_min:.1f}% < Q+5% = {Q+5:.1f}%). "
                       f"Proceed to Stage 2 (test 6 more units)."),
            detail=[f"Q={Q:.1f}%", f"S1 min {s1_min:.1f}% < required {Q+5:.1f}%",
                    "Stage 2 testing required before any disposition."],
            standard_reference=ref,
            capa_action="Stage advancement required — not yet OOS.",
        )

    # ── Stage 2 (12 units total) ──
    all12 = list(s1_results) + list(s2_results)
    avg12 = mean(all12)
    min12 = min(all12)
    s2_pass = (avg12 >= Q) and (min12 >= Q - 15)
    if s2_pass:
        return CompendialVerdict(
            chapter="USP <711>", test="Dissolution (Immediate-Release)",
            stage_reached="S2", passed=True, oos=False,
            rationale=(f"S2 met: average of 12 = {avg12:.1f}% >= Q ({Q:.1f}%) and "
                       f"no unit < Q-15% ({Q-15:.1f}%)."),
            detail=[f"Q={Q:.1f}%", f"avg(12)={avg12:.1f}%", f"min(12)={min12:.1f}%",
                    f"S2 acceptance = avg>=Q and no unit < {Q-15:.1f}%"],
            standard_reference=ref,
        )

    if not s3_results:
        return CompendialVerdict(
            chapter="USP <711>", test="Dissolution (Immediate-Release)",
            stage_reached="S2", passed=False, oos=False,
            rationale=(f"S2 not met (avg {avg12:.1f}%, min {min12:.1f}%). "
                       f"Proceed to Stage 3 (test 12 more units)."),
            detail=[f"Q={Q:.1f}%", f"avg(12)={avg12:.1f}%", f"min(12)={min12:.1f}%"],
            standard_reference=ref,
            capa_action="Stage advancement required — not yet OOS.",
        )

    # ── Stage 3 (24 units total) ──
    all24 = all12 + list(s3_results)
    avg24 = mean(all24)
    min24 = min(all24)
    n_below_15 = sum(1 for v in all24 if v < Q - 15)
    s3_pass = (avg24 >= Q) and (n_below_15 <= 2) and (min24 >= Q - 25)
    if s3_pass:
        return CompendialVerdict(
            chapter="USP <711>", test="Dissolution (Immediate-Release)",
            stage_reached="S3", passed=True, oos=False,
            rationale=(f"S3 met: average of 24 = {avg24:.1f}% >= Q, "
                       f"{n_below_15} unit(s) < Q-15% (<=2 allowed), "
                       f"and no unit < Q-25% ({Q-25:.1f}%)."),
            detail=[f"Q={Q:.1f}%", f"avg(24)={avg24:.1f}%",
                    f"units < Q-15% ({Q-15:.1f}%): {n_below_15}",
                    f"min(24)={min24:.1f}%"],
            standard_reference=ref,
        )

    # OOS — auto-open CAPA
    reasons = []
    if avg24 < Q:               reasons.append(f"avg(24)={avg24:.1f}% < Q ({Q:.1f}%)")
    if n_below_15 > 2:          reasons.append(f"{n_below_15} units < Q-15% (>2)")
    if min24 < Q - 25:          reasons.append(f"a unit < Q-25% ({Q-25:.1f}%): min={min24:.1f}%")
    return CompendialVerdict(
        chapter="USP <711>", test="Dissolution (Immediate-Release)",
        stage_reached="S3", passed=False, oos=True,
        rationale="S3 failed — dissolution OOS. " + "; ".join(reasons),
        detail=[f"Q={Q:.1f}%", f"avg(24)={avg24:.1f}%",
                f"units < Q-15%: {n_below_15}", f"min(24)={min24:.1f}%"],
        standard_reference=ref,
        capa_action=("Auto-open OOS deviation/CAPA, hold batch, trigger investigation "
                     "per USP <1092>."),
    )


# ── USP <905> Uniformity of Dosage Units (Content Uniformity) ────────────────
def evaluate_uniformity(
    results: List[float],
    label_claim: float = 100.0,
    L1: float = 15.0,
    L2: float = 25.0,
) -> CompendialVerdict:
    """Acceptance Value (AV) evaluation for Content Uniformity.

    Implements the AV formula from <905>:
        M (reference value) uses the 98.5–101.5% indifference zone around the
        target T (=100% here, expressed relative to label claim):
            if 98.5 <= X_bar <= 101.5:  M = X_bar,   AV = k*s
            if X_bar < 98.5:            M = 98.5,     AV = (M - X_bar) + k*s
            if X_bar > 101.5:           M = 101.5,    AV = (X_bar - M) + k*s
        k = 2.4 at n=10 (Stage 1), k = 2.0 at n=30 (Stage 2).

    Stage 1 (n=10): pass if AV <= L1 (default 15.0).
    Stage 2 (n=30): pass if AV <= L1 AND every unit within [(1-0.01*L2)*M,
                    (1+0.01*L2)*M] (default M +/- 25%).
    """
    ref = "USP <905> Uniformity of Dosage Units"
    n = len(results)
    if n not in (10, 30):
        raise ValueError("Provide 10 results (Stage 1) or 30 results (Stage 2).")

    # Express results as % of label claim
    xbar = mean(results)
    s = pstdev(results) if n > 1 else 0.0
    k = 2.4 if n == 10 else 2.0

    if 98.5 <= xbar <= 101.5:
        M = xbar
        av = k * s
    elif xbar < 98.5:
        M = 98.5
        av = (M - xbar) + k * s
    else:
        M = 101.5
        av = (xbar - M) + k * s

    stage = "L1" if n == 10 else "L2"
    av_ok = av <= L1

    if n == 10:
        if av_ok:
            return CompendialVerdict(
                chapter="USP <905>", test="Content Uniformity",
                stage_reached="Stage 1 (n=10)", passed=True, oos=False,
                rationale=f"Stage 1 met: AV={av:.1f} <= L1 ({L1:.1f}).",
                detail=[f"mean={xbar:.2f}%", f"SD={s:.2f}", f"k={k}", f"M={M:.2f}", f"AV={av:.2f}"],
                standard_reference=ref,
            )
        return CompendialVerdict(
            chapter="USP <905>", test="Content Uniformity",
            stage_reached="Stage 1 (n=10)", passed=False, oos=False,
            rationale=(f"Stage 1 not met: AV={av:.1f} > L1 ({L1:.1f}). "
                       f"Proceed to Stage 2 (test 20 more units, n=30)."),
            detail=[f"mean={xbar:.2f}%", f"SD={s:.2f}", f"AV={av:.2f}"],
            standard_reference=ref,
            capa_action="Stage advancement required — not yet OOS.",
        )

    # n == 30 (Stage 2)
    lo = (1 - 0.01 * L2) * M
    hi = (1 + 0.01 * L2) * M
    within = all(lo <= v <= hi for v in results)
    if av_ok and within:
        return CompendialVerdict(
            chapter="USP <905>", test="Content Uniformity",
            stage_reached="Stage 2 (n=30)", passed=True, oos=False,
            rationale=(f"Stage 2 met: AV={av:.1f} <= L1 ({L1:.1f}) and all units "
                       f"within [{lo:.1f}, {hi:.1f}] (M +/- {L2:.0f}%)."),
            detail=[f"mean={xbar:.2f}%", f"SD={s:.2f}", f"AV={av:.2f}",
                    f"range=[{lo:.1f}, {hi:.1f}]"],
            standard_reference=ref,
        )
    reasons = []
    if not av_ok:   reasons.append(f"AV={av:.1f} > L1 ({L1:.1f})")
    if not within:  reasons.append(f"unit(s) outside [{lo:.1f}, {hi:.1f}]")
    return CompendialVerdict(
        chapter="USP <905>", test="Content Uniformity",
        stage_reached="Stage 2 (n=30)", passed=False, oos=True,
        rationale="Stage 2 failed — uniformity OOS. " + "; ".join(reasons),
        detail=[f"mean={xbar:.2f}%", f"SD={s:.2f}", f"AV={av:.2f}",
                f"allowed range=[{lo:.1f}, {hi:.1f}]"],
        standard_reference=ref,
        capa_action="Auto-open OOS deviation/CAPA; batch typically rejected.",
    )


# ── USP <788>/<789> Particulate Matter ──────────────────────────────────────
def evaluate_particulates(
    count_10um: float,
    count_25um: float,
    product_type: str,
    count_50um: Optional[float] = None,
    volume_ml: Optional[float] = None,
) -> CompendialVerdict:
    """Light-obscuration particulate limits.

    product_type:
        "SVP"  small-volume parenteral (<=100 mL) — <788> per-container totals
        "LVP"  large-volume parenteral (>100 mL)  — <788> per-mL
        "ophthalmic"                               — <789> per-mL (intraocular)

    For SVP, counts are per-container averages; for LVP/ophthalmic, per-mL.
    """
    ref788 = "USP <788> Particulate Matter in Injections (Method 1)"
    ref789 = "USP <789> Particulate Matter in Ophthalmic Solutions"
    pt = (product_type or "").strip().lower()

    if pt in ("svp", "small", "small-volume", "small_volume"):
        lim10, lim25, ref, basis = 6000, 600, ref788, "per container"
        fail = (count_10um > lim10) or (count_25um > lim25)
        detail = [f">=10um: {count_10um:.0f} (limit {lim10}/container)",
                  f">=25um: {count_25um:.0f} (limit {lim25}/container)"]
    elif pt in ("lvp", "large", "large-volume", "large_volume"):
        lim10, lim25, ref, basis = 25, 3, ref788, "per mL"
        fail = (count_10um > lim10) or (count_25um > lim25)
        detail = [f">=10um: {count_10um:.1f}/mL (limit {lim10}/mL)",
                  f">=25um: {count_25um:.1f}/mL (limit {lim25}/mL)"]
    elif pt in ("ophthalmic", "intraocular", "eye"):
        lim10, lim25, lim50, ref, basis = 50, 5, 2, ref789, "per mL"
        c50 = count_50um if count_50um is not None else 0.0
        fail = (count_10um > lim10) or (count_25um > lim25) or (c50 > lim50)
        detail = [f">=10um: {count_10um:.1f}/mL (limit {lim10}/mL)",
                  f">=25um: {count_25um:.1f}/mL (limit {lim25}/mL)",
                  f">=50um: {c50:.1f}/mL (limit {lim50}/mL)"]
    else:
        raise ValueError("product_type must be 'SVP', 'LVP', or 'ophthalmic'.")

    chapter = "USP <789>" if pt in ("ophthalmic", "intraocular", "eye") else "USP <788>"
    if fail:
        return CompendialVerdict(
            chapter=chapter, test=f"Particulate Matter ({basis})",
            stage_reached="Method 1", passed=False, oos=True,
            rationale="Particulate limit exceeded — OOS.",
            detail=detail, standard_reference=ref,
            capa_action="Open OOS deviation, hold lot. If Method 1 unsuitable "
                        "(opaque/viscous), route to Method 2 (microscopic) — Method 2 "
                        "cannot pass a lot that already failed Method 1.",
        )
    return CompendialVerdict(
        chapter=chapter, test=f"Particulate Matter ({basis})",
        stage_reached="Method 1", passed=True, oos=False,
        rationale="Within particulate limits.",
        detail=detail, standard_reference=ref,
    )


# Convenience registry (for catalog/discovery)
USP_EVALUATORS = {
    "dissolution_711": evaluate_dissolution,
    "uniformity_905": evaluate_uniformity,
    "particulates_788_789": evaluate_particulates,
}
