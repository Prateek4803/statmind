# StatMind — Process Statistics Platform

[![Live](https://img.shields.io/badge/live-www.statmind.tech-4f8ef7?style=flat-square)](https://www.statmind.tech)
[![Status](https://img.shields.io/badge/status-public%20beta-green?style=flat-square)](https://www.statmind.tech)
[![Python](https://img.shields.io/badge/python-3.12-blue?style=flat-square)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-gray?style=flat-square)](LICENSE)

**A Minitab-grade process statistics engine for quality engineers — free, browser-based, no install.**

→ **[www.statmind.tech](https://www.statmind.tech)**

---

## What it does

Upload a CSV or Excel file. Get full statistical analysis in seconds. Export a PDF report.

No license fee. No IT ticket. No installation. Runs entirely in your browser.

| Module | What it computes |
|---|---|
| **Normality** | Shapiro-Wilk, Anderson-Darling, Ryan-Joiner |
| **Capability** | Cp, Cpk, Pp, Ppk with Bissell 95% CI · ISO 22514 non-normal |
| **SPC** | I-MR, Xbar-R, Xbar-S, CUSUM, EWMA, Run Chart |
| **Gauge R&R** | Two-way ANOVA, %GRR, ndc, Repeatability/Reproducibility |
| **DOE** | Full/fractional factorial, CCD, Box-Behnken RSM |
| **Regression** | Multiple linear, logistic (ROC/AUC), stepwise (AIC/BIC) |
| **Multivariate** | PCA with biplots, scatter matrix, correlation heatmap |
| **Reliability** | Weibull 2/3-param, B10/B50 life, Kaplan-Meier survival |
| **CAPA Engine** | 93 rules across 16 process families — auto-generates 8D reports |
| **PDF Report** | Full analysis session export — one click |

**43 live tools · 93 CAPA rules · 145+ API endpoints**

---

## Why StatMind

| | Minitab | StatMind |
|---|---|---|
| Price | $1,800/user/year | Free (Pro coming) |
| Install | Desktop app required | Browser — zero install |
| CAPA intelligence | Manual | Auto-generated, domain-aware |
| Industries covered | General | Semiconductor, Automotive, Aerospace, Medical, CMM |
| Standards | AIAG, ISO | AIAG · ISO · SEMI · AS9100 · IATF 16949 · ISO 13485 |

---

## Industry coverage

| Industry | Standards |
|---|---|
| Semiconductor (Etch, CMP, Litho, Diffusion, CVD) | SEMI E10 / E35 |
| Automotive | IATF 16949 · PPAP |
| Aerospace | AS9100D |
| Medical Device | ISO 13485 · FDA 21 CFR |
| CMM / GD&T | ASME Y14.5 |
| General / Lab | ISO 17025 |

---

## Stack

**Backend** — Python 3.12, FastAPI, Gunicorn, uvicorn  
**Compute** — numpy, scipy, statsmodels, pandas, pingouin  
**Reports** — ReportLab (PDF), openpyxl (Excel)  
**Frontend** — Vanilla JS, Chart.js 4.4, single-page app  
**Database** — SQLAlchemy + SQLite (PostgreSQL-ready)  
**Infra** — AWS EC2 t3.small, Docker, nginx, systemd  
**CI/CD** — GitHub Actions → SSH deploy to EC2  

---

## Running locally

```bash
git clone https://github.com/Prateek4803/statmind.git
cd statmind
pip install -r requirements.txt
uvicorn main:app --port 8000
# Open http://localhost:8000
```

---

## API

FastAPI auto-generates interactive docs at:

```
https://www.statmind.tech/api/docs
```

Health check:
```bash
curl https://www.statmind.tech/api/v1/health
```

---

## Standards

AIAG SPC 2nd Ed. · AIAG MSA 4th Ed. · ISO 22514-2 · IATF 16949 · AS9100D · ISO 13485 · SEMI E10 · ASTM E2281 · IPC-A-610

---

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

*StatMind v5.0 · Public Beta · Built for quality engineers who are tired of waiting for IT to approve Minitab licenses.*
