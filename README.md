# StatMind — Process Statistics Platform

Live: **https://www.statmind.tech**

A complete process statistics engine for quality engineers.
No license. No install. Upload a CSV and get results in 60 seconds.

## What it does

| Module | What it computes |
|---|---|
| Normality | Shapiro-Wilk, Anderson-Darling, Ryan-Joiner |
| Capability | Cp, Cpk, Pp, Ppk with Bissell 95% CI |
| SPC | I-MR, Xbar-R, Xbar-S, CUSUM, EWMA, Run Chart |
| Gauge R&R | Two-way ANOVA, %GRR, ndc, variance decomposition |
| DOE | Full/fractional factorial, CCD, Box-Behnken RSM |
| CAPA Engine | 93 rules across 16 process families |
| PDF Report | Full analysis session export |

## Stack

- **Backend:** Python 3.12, FastAPI, Gunicorn, uvicorn
- **Compute:** numpy, scipy, statsmodels, pandas, pingouin
- **Frontend:** Vanilla JS, Chart.js 4.4
- **Infra:** AWS EC2 t3.small, Docker, nginx, systemd
- **CI/CD:** GitHub Actions → SSH deploy to EC2

## Running locally

```bash
git clone https://github.com/Prateek4803/statmind.git
cd statmind
pip install -r requirements.txt
uvicorn main:app --port 8000
# Open http://localhost:8000
```

## Standards coverage

AIAG SPC 2nd Ed. · AIAG MSA 4th Ed. · ISO 22514 · IATF 16949 · AS9100D · ISO 13485