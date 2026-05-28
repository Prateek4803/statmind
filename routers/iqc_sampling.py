"""
StatMind — IQC / AQL Sampling Plan (ANSI/ASQ Z1.4 + Z1.9)
Apple: "Lead IQC/IPQC/OQC". Amazon: "receiving/source inspection, FAI".
Google: "incoming quality control". 
Generates sampling plan, returns accept/reject decision.
Z1.4 = Attribute sampling (pass/fail, visual)
Z1.9 = Variable sampling (measured dimensions)
"""
import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import Optional

# ANSI/ASQ Z1.4 Table — Sample Size Code Letters
# (lot_size_range) → code_letter
LOT_SIZE_CODES = [
    (2, 8, "A"), (9, 15, "B"), (16, 25, "C"), (26, 50, "D"),
    (51, 90, "E"), (91, 150, "F"), (151, 280, "G"), (281, 500, "H"),
    (501, 1200, "J"), (1201, 3200, "K"), (3201, 10000, "L"),
    (10001, 35000, "M"), (35001, 150000, "N"), (150001, 500000, "P"),
    (500001, float('inf'), "Q"),
]

# Z1.4 Normal inspection sample sizes by code letter
Z14_SAMPLE_SIZES = {
    "A":2,"B":3,"C":5,"D":8,"E":13,"F":20,"G":32,"H":50,
    "J":80,"K":125,"L":200,"M":315,"N":500,"P":800,"Q":1250,
}

# Z1.4 Ac/Re (Accept/Reject numbers) for AQL levels
# Format: {code_letter: {aql: (Ac, Re)}}
Z14_AC_RE = {
    "A": {0.065:(0,1),0.1:(0,1),0.15:(0,1),0.25:(0,1),0.4:(0,1),0.65:(0,1),1.0:(0,1),1.5:(0,1),2.5:(0,1),4.0:(0,1),6.5:(0,1),10.0:(0,1)},
    "B": {0.065:(0,1),0.1:(0,1),0.15:(0,1),0.25:(0,1),0.4:(0,1),0.65:(0,1),1.0:(0,1),1.5:(0,1),2.5:(0,1),4.0:(0,1),6.5:(0,1),10.0:(0,1)},
    "C": {0.4:(0,1),0.65:(0,1),1.0:(0,1),1.5:(0,1),2.5:(0,1),4.0:(0,1),6.5:(0,1),10.0:(1,2)},
    "D": {0.25:(0,1),0.4:(0,1),0.65:(0,1),1.0:(0,1),1.5:(0,1),2.5:(0,1),4.0:(1,2),6.5:(1,2),10.0:(2,3)},
    "E": {0.15:(0,1),0.25:(0,1),0.4:(0,1),0.65:(0,1),1.0:(0,1),1.5:(0,1),2.5:(1,2),4.0:(1,2),6.5:(2,3),10.0:(3,4)},
    "F": {0.1:(0,1),0.15:(0,1),0.25:(0,1),0.4:(0,1),0.65:(0,1),1.0:(0,1),1.5:(1,2),2.5:(1,2),4.0:(2,3),6.5:(3,4),10.0:(5,6)},
    "G": {0.065:(0,1),0.1:(0,1),0.15:(0,1),0.25:(0,1),0.4:(0,1),0.65:(0,1),1.0:(1,2),1.5:(1,2),2.5:(2,3),4.0:(3,4),6.5:(5,6),10.0:(7,8)},
    "H": {0.065:(0,1),0.1:(0,1),0.15:(0,1),0.25:(0,1),0.4:(0,1),0.65:(1,2),1.0:(1,2),1.5:(2,3),2.5:(3,4),4.0:(5,6),6.5:(7,8),10.0:(10,11)},
    "J": {0.065:(0,1),0.1:(0,1),0.15:(0,1),0.25:(0,1),0.4:(1,2),0.65:(1,2),1.0:(2,3),1.5:(3,4),2.5:(5,6),4.0:(7,8),6.5:(10,11),10.0:(14,15)},
    "K": {0.065:(0,1),0.1:(0,1),0.15:(0,1),0.25:(1,2),0.4:(1,2),0.65:(2,3),1.0:(3,4),1.5:(5,6),2.5:(7,8),4.0:(10,11),6.5:(14,15),10.0:(21,22)},
    "L": {0.065:(0,1),0.1:(0,1),0.15:(1,2),0.25:(1,2),0.4:(2,3),0.65:(3,4),1.0:(5,6),1.5:(7,8),2.5:(10,11),4.0:(14,15),6.5:(21,22)},
    "M": {0.065:(0,1),0.1:(1,2),0.15:(1,2),0.25:(2,3),0.4:(3,4),0.65:(5,6),1.0:(7,8),1.5:(10,11),2.5:(14,15),4.0:(21,22)},
    "N": {0.065:(1,2),0.1:(1,2),0.15:(2,3),0.25:(3,4),0.4:(5,6),0.65:(7,8),1.0:(10,11),1.5:(14,15),2.5:(21,22)},
    "P": {0.065:(1,2),0.1:(2,3),0.15:(3,4),0.25:(5,6),0.4:(7,8),0.65:(10,11),1.0:(14,15),1.5:(21,22)},
    "Q": {0.065:(2,3),0.1:(3,4),0.15:(5,6),0.25:(7,8),0.4:(10,11),0.65:(14,15),1.0:(21,22)},
}

AQL_LEVELS = [0.065, 0.1, 0.15, 0.25, 0.4, 0.65, 1.0, 1.5, 2.5, 4.0, 6.5, 10.0]

@dataclass
class SamplingPlan:
    plan_type: str          # "Z1.4 Attribute" or "Z1.9 Variable"
    lot_size: int
    aql: float
    inspection_level: str   # "I", "II", "III" (II = normal)
    code_letter: str
    sample_size: int
    accept_number: int      # Ac
    reject_number: int      # Re
    # Inspection result (if defects provided)
    defects_found: Optional[int]
    disposition: str        # "ACCEPT", "REJECT", "PENDING"
    # Risk metrics
    producer_risk_pct: float  # α — P(reject good lot)
    consumer_risk_pct: float  # β — P(accept bad lot) at RQL/LTPD
    ltpd: float               # Lot Tolerance Percent Defective (10% consumer risk)
    # For Z1.9 variable
    z19_k_value: Optional[float]
    z19_sample_mean: Optional[float]
    z19_sample_std: Optional[float]
    z19_quality_index_upper: Optional[float]
    z19_quality_index_lower: Optional[float]
    # Narrative
    plan_description: str
    conclusion: str

def _get_code_letter(lot_size: int, inspection_level: str = "II") -> str:
    # Level II is normal. Level I reduces by ~2 code letters, Level III adds ~2
    level_offset = {"I": -2, "II": 0, "III": 2}
    offset = level_offset.get(inspection_level, 0)
    for lo, hi, code in LOT_SIZE_CODES:
        if lo <= lot_size <= hi:
            # Shift code letter
            letters = "ABCDEFGHJKLMNPQ"
            idx = letters.index(code)
            new_idx = max(0, min(len(letters)-1, idx + offset))
            return letters[new_idx]
    return "Q"

def _closest_aql(aql: float) -> float:
    return min(AQL_LEVELS, key=lambda x: abs(x - aql))

def generate_sampling_plan(
    lot_size: int,
    aql: float = 1.0,
    inspection_level: str = "II",
    defects_found: int = None,
    # Z1.9 variable inputs
    usl: float = None,
    lsl: float = None,
    sample_data: list = None,
) -> SamplingPlan:
    aql_use = _closest_aql(aql)
    code = _get_code_letter(lot_size, inspection_level)
    n = Z14_SAMPLE_SIZES.get(code, 125)
    ac_re = Z14_AC_RE.get(code, {}).get(aql_use)

    # If exact AQL not found for this code, find next available
    if ac_re is None:
        for a in sorted(Z14_AC_RE.get(code, {}).keys()):
            if a >= aql_use:
                ac_re = Z14_AC_RE[code][a]
                aql_use = a
                break
    if ac_re is None:
        ac_re = (0, 1)

    ac, re = ac_re

    # Disposition
    if defects_found is not None:
        disposition = "ACCEPT" if defects_found <= ac else "REJECT"
    else:
        disposition = "PENDING"

    # Risk calculation via binomial
    p_aql = aql_use / 100
    # Producer risk: P(reject | p=AQL)
    prod_risk = float(1 - stats.binom.cdf(ac, n, p_aql)) * 100
    # Consumer risk at LTPD: find LTPD where P(accept) = 10%
    ltpd = float(stats.beta.ppf(0.9, ac + 1, n - ac) * 100) if ac >= 0 else aql_use * 10
    cons_risk = float(stats.binom.cdf(ac, n, ltpd/100)) * 100

    plan_desc = (
        f"ANSI/ASQ Z1.4 Normal Inspection Level {inspection_level}. "
        f"Lot size {lot_size:,} → Code letter {code}. "
        f"Sample n={n}, AQL={aql_use}%, Ac={ac}, Re={re}."
    )

    # Z1.9 variable analysis if data provided
    k_val = z19_mean = z19_std = qi_u = qi_l = None
    plan_type = "Z1.4 Attribute"
    if sample_data and usl and lsl:
        plan_type = "Z1.9 Variable"
        arr = np.array(sample_data, dtype=float)
        z19_mean = float(np.mean(arr))
        z19_std = float(np.std(arr, ddof=1))
        # K value for Z1.9 (lookup by n and AQL — simplified: k ≈ 1.5 for AQL 1.0, n=32)
        k_val = round(float(stats.norm.ppf(1 - aql_use/100)) - 1.0/np.sqrt(n), 4)
        if z19_std > 0:
            qi_u = round((usl - z19_mean) / z19_std, 4)
            qi_l = round((z19_mean - lsl) / z19_std, 4)
            z19_accept = (qi_u >= k_val and qi_l >= k_val)
            if defects_found is None:
                disposition = "ACCEPT" if z19_accept else "REJECT"

    conclusion = (
        f"{plan_type} sampling plan: n={n}, Ac={ac}, Re={re} (AQL={aql_use}%). "
        f"{'Inspect ' + str(n) + ' units. ' if defects_found is None else ''}"
        + (f"Found {defects_found} defect(s) → {disposition}. " if defects_found is not None else "")
        + f"Producer risk α={prod_risk:.1f}%, Consumer risk β={cons_risk:.1f}% at LTPD={ltpd:.2f}%."
    )

    return SamplingPlan(
        plan_type=plan_type, lot_size=lot_size, aql=aql_use,
        inspection_level=inspection_level, code_letter=code,
        sample_size=n, accept_number=ac, reject_number=re,
        defects_found=defects_found, disposition=disposition,
        producer_risk_pct=round(prod_risk,2), consumer_risk_pct=round(cons_risk,2),
        ltpd=round(ltpd,3),
        z19_k_value=k_val, z19_sample_mean=round(z19_mean,5) if z19_mean else None,
        z19_sample_std=round(z19_std,5) if z19_std else None,
        z19_quality_index_upper=qi_u, z19_quality_index_lower=qi_l,
        plan_description=plan_desc, conclusion=conclusion,
    )
