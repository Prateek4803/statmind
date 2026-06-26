"""
ai_explainer/grounding.py — The safety-critical grounding layer.

This is the heart of StatMind's LLM explainer. Its job is to make it
*structurally hard* for the model to mislead: the LLM never sees raw data,
never recomputes anything, and is given an explicit, bounded set of verified
facts plus strict instructions to explain ONLY those.

WHY THIS MATTERS
----------------
StatMind's whole value is trustworthy numbers. An LLM that "interprets" results
can fluently invent a Cpk, misread a verdict, or contradict the verified engine.
The defense is grounding: the deterministic engine computes the facts; the LLM
only narrates the facts it is handed. If a fact isn't in the grounding payload,
the model is instructed it does not know it.

This module is provider-agnostic — it builds the prompt; it does not call any
model. That keeps the trust logic independent of whether the backend is a hosted
API or a local model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# The system instruction is the contract. It is deliberately strict.
SYSTEM_INSTRUCTION = """You are StatMind's analysis explainer. You help a quality \
engineer understand a statistical result that has ALREADY been computed by \
StatMind's verified statistical engine.

ABSOLUTE RULES — these are not style preferences, they are hard constraints:
1. Explain ONLY the numbers and verdict provided in the FACTS block below. \
These are authoritative and already verified. Do not recompute them.
2. NEVER invent, estimate, or infer a numeric value that is not in the FACTS. \
If asked about a number you were not given, say you don't have that value \
rather than guessing.
3. NEVER contradict the provided verdict. The engine decided it; your job is to \
explain WHY it makes sense given the numbers, in plain language.
4. If the user asks something the FACTS cannot answer (e.g. "what caused this?", \
which requires process knowledge you don't have), say so plainly and suggest \
what analysis or information would help — do not speculate as if it were fact.
5. Be concise and practical. You are talking to a working engineer, not a \
student. Lead with what the result means for their process and what they might \
do next.
6. You do not make the decision. You explain and advise; the engineer decides."""


@dataclass
class GroundingPayload:
    """Everything the model is allowed to know about one analysis result."""
    analysis_type: str
    facts: dict          # the verified, explainable scalar facts
    verdict: Optional[str]
    verdict_detail: Optional[str]

    def to_facts_block(self) -> str:
        lines = [f"ANALYSIS TYPE: {self.analysis_type}"]
        if self.verdict:
            lines.append(f"VERDICT (authoritative): {self.verdict}")
        if self.verdict_detail:
            lines.append(f"VERDICT DETAIL: {self.verdict_detail}")
        lines.append("VERIFIED FACTS:")
        for k, v in self.facts.items():
            lines.append(f"  - {k}: {v}")
        return "\n".join(lines)


# ── Fact extractors: pull ONLY safe scalar facts from each result type ───────
# We deliberately exclude raw arrays (histogram data, curve points, raw values)
# — the model never needs them and shouldn't see them.

def _round(v, n=4):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return v


def _extract_capability(r: dict) -> GroundingPayload:
    keys = ["column", "n", "mean", "std_within", "std_overall", "usl", "lsl",
            "target", "cp", "cpk", "pp", "ppk", "cpu", "cpl",
            "ppm_within", "ppm_overall", "sigma_level"]
    facts = {k: _round(r.get(k)) for k in keys if r.get(k) is not None}
    # Confidence interval is meaningful — include the 95% one compactly
    ci = r.get("cpk_ci_95")
    if isinstance(ci, dict):
        facts["cpk_95%_CI"] = f"[{_round(ci.get('lower'))}, {_round(ci.get('upper'))}]"
    return GroundingPayload("Process Capability", facts,
                            r.get("verdict"), r.get("verdict_detail"))


def _extract_spc(r: dict) -> GroundingPayload:
    keys = ["column", "chart_type", "n", "center_line", "ucl", "lcl",
            "in_control", "total_alarms"]
    facts = {k: _round(r.get(k)) for k in keys if r.get(k) is not None}
    return GroundingPayload("Statistical Process Control (Control Chart)", facts,
                            "In Control" if r.get("in_control") else "Out of Control",
                            r.get("verdict_detail"))


def _extract_normality(r: dict) -> GroundingPayload:
    keys = ["column", "n", "mean", "std", "skewness", "kurtosis",
            "shapiro_stat", "shapiro_p", "anderson_stat"]
    facts = {k: _round(r.get(k)) for k in keys if r.get(k) is not None}
    return GroundingPayload("Normality Test", facts,
                            r.get("overall_verdict") or r.get("verdict"),
                            r.get("verdict_detail"))


def _extract_grr(r: dict) -> GroundingPayload:
    facts = {}
    for sub in ["gauge_rr", "repeatability", "reproducibility", "part_to_part"]:
        node = r.get(sub)
        if isinstance(node, dict) and node.get("pct_study_var") is not None:
            facts[f"{sub}_%study_var"] = _round(node["pct_study_var"], 1)
    for k in ["ndc", "n_parts", "n_operators", "n_reps"]:
        if r.get(k) is not None:
            facts[k] = r.get(k)
    return GroundingPayload("Gauge R&R (Measurement System Analysis)", facts,
                            r.get("verdict"), r.get("verdict_detail"))


def _extract_generic(analysis_type: str, r: dict) -> GroundingPayload:
    """Fallback extractor for any analysis type without a bespoke extractor.

    Safely pulls only SCALAR facts (numbers, short strings, bools) from the
    result dict and excludes raw data arrays / nested chart payloads, preserving
    the no-raw-data guarantee universally. This is what makes 'explain on every
    analysis' a property of the architecture rather than 30 hand-written cases.
    """
    EXCLUDE_HINTS = ("data", "curve", "histogram", "_x", "_y", "points",
                     "bins", "raw", "values", "series", "chart")
    facts = {}
    for k, v in (r or {}).items():
        kl = k.lower()
        if any(h in kl for h in EXCLUDE_HINTS):
            continue
        # Only keep scalars and short strings; skip arrays/dicts (raw payloads).
        if isinstance(v, bool):
            facts[k] = v
        elif isinstance(v, (int, float)):
            facts[k] = _round(v)
        elif isinstance(v, str) and len(v) <= 200:
            facts[k] = v
        # lists/dicts deliberately skipped — never send raw structures
        if len(facts) >= 25:  # keep the prompt bounded
            break
    pretty = (analysis_type or "Analysis").replace("_", " ").title()
    return GroundingPayload(pretty, facts,
                            r.get("verdict") or r.get("overall_verdict"),
                            r.get("verdict_detail"))


_EXTRACTORS = {
    "capability": _extract_capability,
    "spc": _extract_spc,
    "normality": _extract_normality,
    "grr": _extract_grr,
}


def build_grounding(analysis_type: str, result: dict) -> Optional[GroundingPayload]:
    """Extract the safe, verified facts for an analysis result.

    Uses a bespoke extractor when one exists for the analysis type; otherwise
    falls back to a generic scalar extractor so EVERY analysis can be explained
    while still never leaking raw data. Returns None only if there are no usable
    facts at all (caller then declines cleanly)."""
    at = (analysis_type or "").strip().lower()
    fn = _EXTRACTORS.get(at)
    payload = fn(result or {}) if fn else _extract_generic(at, result or {})
    # If even the generic extractor found nothing useful, decline.
    if not payload.facts and not payload.verdict:
        return None
    return payload


def build_messages(analysis_type: str, result: dict,
                   user_question: Optional[str] = None) -> Optional[list[dict]]:
    """Build the full message list for the LLM: system contract + facts +
    (optional) the user's question. Returns None if the analysis type isn't
    supported, so the caller can decline cleanly.

    If user_question is None, the model is asked for a default plain-language
    explanation of the result.
    """
    grounding = build_grounding(analysis_type, result)
    if grounding is None:
        return None

    facts_block = grounding.to_facts_block()
    if user_question and user_question.strip():
        user_content = (
            f"{facts_block}\n\n"
            f"The engineer asks: {user_question.strip()}\n\n"
            f"Answer using only the verified facts above."
        )
    else:
        user_content = (
            f"{facts_block}\n\n"
            f"Explain this result in plain language: what it means for the "
            f"process, why the verdict makes sense, and what the engineer "
            f"should consider next. Use only the verified facts above."
        )

    return [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": user_content},
    ]
