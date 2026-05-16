"""
StatMind P1-C — Fishbone (Ishikawa) Diagram Builder
Interactive cause-effect diagram with 6M branches.
CAPA engine outputs auto-populate cause branches.
In-memory store supports multiple diagrams.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class FishboneCause:
    id: str
    branch: str          # "Machine","Method","Material","Man","Measurement","Mother_Nature"
    cause: str
    sub_causes: list     # list of strings
    from_capa: bool      # was this auto-populated from CAPA engine?
    severity: str        # "high","medium","low"
    verified: bool       # has root cause been confirmed?

@dataclass
class FishboneDiagram:
    diagram_id: str
    title: str
    effect: str          # the problem statement (head of the fish)
    process: str
    created_at: str
    branches: dict       # {branch_name: [FishboneCause]}
    # Summary
    n_causes: int
    high_severity_count: int
    verified_count: int
    # Chart data for frontend SVG rendering
    chart_data: dict

_diagrams: dict = {}

BRANCH_COLORS = {
    "Machine":      "#2dd4a0",
    "Method":       "#60a5fa",
    "Material":     "#f0b429",
    "Man":          "#f05c5c",
    "Measurement":  "#a78bfa",
    "Mother_Nature":"#34d980",
}

BRANCH_QUESTIONS = {
    "Machine":      ["Is the machine calibrated?","Is there tool wear?","Are fixtures consistent?","Is maintenance up to date?"],
    "Method":       ["Is the process documented?","Are procedures followed?","Is the sequence correct?","Is there operator variation?"],
    "Material":     ["Is incoming material in spec?","Are there lot-to-lot differences?","Is storage correct?","Is there contamination?"],
    "Man":          ["Is training adequate?","Is there operator fatigue?","Are instructions clear?","Is there skill variation?"],
    "Measurement":  ["Is the gauge calibrated?","Is %GRR acceptable?","Is there measurement bias?","Are measurement conditions controlled?"],
    "Mother_Nature":["Is temperature controlled?","Is humidity affecting quality?","Is there vibration interference?","Are environmental specs defined?"],
}

def create_diagram(title: str, effect: str, process: str = "") -> FishboneDiagram:
    did = f"FB-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    branches = {b: [] for b in ["Machine","Method","Material","Man","Measurement","Mother_Nature"]}
    diag = FishboneDiagram(
        diagram_id=did, title=title, effect=effect,
        process=process, created_at=datetime.now().isoformat(),
        branches=branches, n_causes=0, high_severity_count=0, verified_count=0,
        chart_data=_build_chart_data(effect, branches),
    )
    _diagrams[did] = diag
    return diag

def add_cause(diagram_id: str, branch: str, cause: str,
              sub_causes: list = None, severity: str = "medium",
              from_capa: bool = False) -> FishboneDiagram:
    if diagram_id not in _diagrams:
        raise KeyError(f"Diagram {diagram_id} not found.")
    diag = _diagrams[diagram_id]
    branch = branch.replace(" ","_").capitalize()
    if branch not in diag.branches:
        diag.branches[branch] = []
    cid = f"{branch[:3]}-{len(diag.branches[branch])+1:02d}"
    c = FishboneCause(
        id=cid, branch=branch, cause=cause,
        sub_causes=sub_causes or [], from_capa=from_capa,
        severity=severity, verified=False,
    )
    diag.branches[branch].append(c)
    _refresh_counts(diag)
    return diag

def populate_from_capa(diagram_id: str, capa_result: dict) -> FishboneDiagram:
    """Auto-populate branches from CAPA engine output."""
    if diagram_id not in _diagrams:
        raise KeyError(f"Diagram {diagram_id} not found.")
    primary = capa_result.get("primary_capa", {})
    if not primary:
        return _diagrams[diagram_id]

    root_cause = primary.get("root_cause", "")
    alt_causes  = primary.get("alternative_causes", [])
    actions     = primary.get("corrective_actions", [])

    # Map to 6M branches
    mappings = {
        "Machine":      ["tool","equipment","machine","chamber","etch","cmp","laser","press","fixture","head"],
        "Method":       ["process","recipe","procedure","setpoint","parameter","temperature","pressure","flow","speed","time"],
        "Material":     ["material","incoming","batch","lot","substrate","paste","chemical","gas","slurry","wafer"],
        "Man":          ["operator","technician","training","skill","error","human","person","analyst"],
        "Measurement":  ["gauge","grr","measurement","sensor","probe","calibrat","inspect","cmm","spi"],
        "Mother_Nature":["temperature","humidity","vibration","environment","electro","static","contamination","particle"],
    }

    def branch_for(text: str) -> str:
        t = text.lower()
        for branch, keywords in mappings.items():
            if any(k in t for k in keywords):
                return branch
        return "Method"

    # Add root cause to appropriate branch
    if root_cause:
        b = branch_for(root_cause)
        add_cause(diagram_id, b, root_cause[:80], severity="high", from_capa=True)

    # Add alternative causes
    for ac in alt_causes[:4]:
        b = branch_for(ac)
        add_cause(diagram_id, b, ac[:80], severity="medium", from_capa=True)

    return _diagrams[diagram_id]

def _refresh_counts(diag: FishboneDiagram):
    all_causes = [c for causes in diag.branches.values() for c in causes]
    diag.n_causes = len(all_causes)
    diag.high_severity_count = sum(1 for c in all_causes if c.severity == "high")
    diag.verified_count = sum(1 for c in all_causes if c.verified)
    diag.chart_data = _build_chart_data(diag.effect, diag.branches)

def _build_chart_data(effect: str, branches: dict) -> dict:
    """Build data structure for frontend SVG rendering."""
    branch_data = []
    for bname, causes in branches.items():
        branch_data.append({
            "name": bname.replace("_"," "),
            "color": BRANCH_COLORS.get(bname, "#888"),
            "causes": [{"id":c.id,"cause":c.cause,"severity":c.severity,
                        "from_capa":c.from_capa,"sub_causes":c.sub_causes} for c in causes],
            "questions": BRANCH_QUESTIONS.get(bname, []),
            "count": len(causes),
        })
    return {
        "effect": effect,
        "branches": branch_data,
        "branch_colors": BRANCH_COLORS,
    }

def get_diagram(did: str) -> FishboneDiagram:
    if did not in _diagrams: raise KeyError(f"Diagram {did} not found.")
    return _diagrams[did]

def list_diagrams() -> list: return list(_diagrams.values())
def delete_diagram(did: str) -> bool:
    if did in _diagrams: del _diagrams[did]; return True
    return False

import dataclasses
def diagram_to_dict(d: FishboneDiagram) -> dict:
    return {
        "diagram_id": d.diagram_id, "title": d.title, "effect": d.effect,
        "process": d.process, "created_at": d.created_at,
        "n_causes": d.n_causes, "high_severity_count": d.high_severity_count,
        "verified_count": d.verified_count, "chart_data": d.chart_data,
        "branches": {k: [dataclasses.asdict(c) for c in v] for k,v in d.branches.items()},
    }
