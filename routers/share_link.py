"""
StatMind N18 — Shareable Analysis Links
Encode analysis results into a URL-safe token.
Recipients can open StatMind and see the exact analysis
without needing to re-upload files or re-run analyses.
No database required — results are compressed into the URL itself.
"""
import json
import gzip
import base64
import hashlib
from datetime import datetime
from dataclasses import dataclass


@dataclass
class ShareableLink:
    token: str          # URL-safe encoded token
    url: str            # full shareable URL
    expires_at: str     # ISO datetime
    parameter: str
    analysis_types: list
    summary: str        # one-line description for link preview
    created_at: str
    token_size_bytes: int


def encode_results(
    results: dict,
    parameter: str = "",
    base_url: str = "https://statmind-production.up.railway.app",
    analysis_types: list = None,
) -> ShareableLink:
    """
    Compress analysis results into a URL-safe token.
    Token contains: parameter name, analysis types, key numerical results.
    Full raw data is NOT included (too large) — only summary statistics.
    """
    # Extract summary data (key numbers only, not raw arrays)
    summary_data = {
        "parameter": parameter,
        "created": datetime.now().isoformat(),
        "analyses": {},
    }

    if "normality" in results:
        n = results["normality"]
        summary_data["analyses"]["normality"] = {
            "verdict": n.get("overall_verdict"),
            "sw_p": n.get("shapiro_wilk", {}).get("p_value"),
            "mean": n.get("descriptive", {}).get("mean"),
            "std": n.get("descriptive", {}).get("std"),
            "n": n.get("descriptive", {}).get("n"),
        }

    if "capability" in results:
        c = results["capability"]
        summary_data["analyses"]["capability"] = {
            "cpk": c.get("cpk"), "cp": c.get("cp"),
            "ppk": c.get("ppk"), "sigma_level": c.get("sigma_level"),
            "ppm_within": c.get("ppm_within"),
            "usl": c.get("usl"), "lsl": c.get("lsl"),
            "mean": c.get("mean"), "std_within": c.get("std_within"),
            "verdict": c.get("verdict"),
        }

    if "spc" in results:
        s = results["spc"]
        summary_data["analyses"]["spc"] = {
            "in_control": s.get("in_control"),
            "total_alarms": s.get("total_alarms"),
            "chart_type": s.get("chart_type"),
            "ucl": s.get("primary_ucl"), "cl": s.get("primary_cl"),
            "lcl": s.get("primary_lcl"),
        }

    if "grr" in results:
        g = results["grr"]
        grr_data = g.get("gauge_rr", {})
        summary_data["analyses"]["grr"] = {
            "pct_study_var": grr_data.get("pct_study_var"),
            "ndc": g.get("ndc"),
            "verdict": g.get("verdict"),
        }

    if "capa" in results:
        ca = results["capa"]
        primary = ca.get("primary_capa", {})
        summary_data["analyses"]["capa"] = {
            "fault_pattern": primary.get("fault_pattern", "")[:80] if primary else "",
            "severity": primary.get("severity", "") if primary else "",
            "match_score": primary.get("match_score", 0) if primary else 0,
        }

    # Encode
    json_bytes = json.dumps(summary_data, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(json_bytes, compresslevel=9)
    token = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")

    # Build URL
    url = f"{base_url}/?share={token}"

    # Build one-line summary
    cpk = summary_data["analyses"].get("capability", {}).get("cpk")
    in_ctrl = summary_data["analyses"].get("spc", {}).get("in_control", True)
    verdict = summary_data["analyses"].get("normality", {}).get("verdict", "")
    summary_parts = []
    if cpk: summary_parts.append(f"Cpk={cpk:.3f}")
    if "spc" in summary_data["analyses"]: summary_parts.append("In control" if in_ctrl else "OUT OF CONTROL")
    if verdict: summary_parts.append(verdict)
    summary_str = f"{parameter}: " + " · ".join(summary_parts) if summary_parts else f"{parameter} analysis"

    return ShareableLink(
        token=token,
        url=url,
        expires_at="Never (self-contained token)",
        parameter=parameter,
        analysis_types=list(summary_data["analyses"].keys()),
        summary=summary_str,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        token_size_bytes=len(token),
    )


def decode_share_token(token: str) -> dict:
    """Decode a share token back to summary data."""
    try:
        # Re-add padding
        padded = token + "=" * (4 - len(token) % 4)
        compressed = base64.urlsafe_b64decode(padded)
        json_bytes = gzip.decompress(compressed)
        return json.loads(json_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid or corrupted share token: {e}")
