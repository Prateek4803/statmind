# StatMind — Process Statistics Platform for Quality Engineers

> **Free · Browser-based · No install · No data stored · Public Beta**

A complete quality engineering toolkit — Normality, Capability, SPC, Gauge R&R, DOE, CAPA, Reliability, and more. Powered by a proprietary statistical intelligence engine.

🔗 **Live:** [statmind-production.up.railway.app](https://statmind-production.up.railway.app)

---

## What StatMind Does

Upload your CSV or Excel → full statistical analysis in seconds → PDF report.

| Category | Tools |
|---|---|
| **Normality** | Shapiro-Wilk · Anderson-Darling · Ryan-Joiner · Johnson SU/SB transformation |
| **Capability** | Cp · Cpk · Pp · Ppk · Bissell 95% CI · Non-normal capability (ISO 22514-2) · Capability Sixpack |
| **SPC** | I-MR · Xbar-R · Xbar-S · CUSUM · EWMA · Run Chart · Western Electric + Nelson rules · Batch boundary detection |
| **Gauge R&R** | ANOVA method · %GRR · ndc · Repeatability/Reproducibility · MSA Linearity & Bias |
| **Hypothesis Testing** | 2-sample t (auto-routes Welch/Mann-Whitney) · Paired t · 1-way ANOVA · Kruskal-Wallis · TOST Equivalence · 2-way ANOVA |
| **Regression** | Simple/Multiple linear · Logistic · Stepwise (AIC/BIC) |
| **DOE** | Full factorial · Fractional factorial · CCD · Box-Behnken (RSM) |
| **Multivariate** | PCA with biplots · Scatter matrix · Multi-Vari · Correlation matrix |
| **Outliers** | Grubbs · Rosner ESD · Dixon Q — with ±3σ/±2σ band charts and numbered annotations |
| **Attribute Charts** | p · np · u · c (AIAG SPC 2nd Ed.) |
| **Reliability** | Weibull (2/3-parameter) · B10/B50 life · Kaplan-Meier survival |
| **Quality Workflows** | CAPA Engine · 8D · PFMEA · Fishbone · Control Plan · DMAIC · COPQ · NCR · FRACAS |
| **Reports** | PDF export (Normality + Capability + SPC + GRR + CAPA) |

---

## StatMind Intelligence Engine

The core differentiator: a proprietary, zero-external-API AI reasoning engine built specifically for quality engineering.

**Components:**
- **Bayesian Confidence Scorer** — calibrated priors from manufacturing experience; computes posterior confidence for each statistical signal
- **TF-IDF Semantic Matcher** — maps parameter names to process families using 80+ manufacturing domain tokens
- **Cross-Signal Analyser** — correlates Cpk + SPC + GRR + normality into a unified differential diagnosis
- **Narrative Engine** — generates plain-English analysis grounded in actual numbers from your data
- **8D Report Generator** — auto-populates D0–D8 from statistical inputs; includes five-whys starter

100% deterministic. Fully auditable. No API calls. No hallucinations.

---

## Running Locally

```bash
# Clone
git clone https://github.com/Prateek4803/statmind.git
cd statmind

# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Run
uvicorn main:app --port 8010
# Open: http://localhost:8010
```

**Requirements:** Python 3.12+

---

## API

All endpoints available at `/api/v1/`. Key endpoints:

```
POST /api/v1/capability/analyze     — Cpk/Ppk with confidence intervals
POST /api/v1/spc/analyze            — Control charts with WE/Nelson rules
POST /api/v1/normality/analyze      — SW/AD/RJ normality tests
POST /api/v1/grr/analyze            — Gauge R&R ANOVA
POST /api/v1/capa/v2/generate       — CAPA rules engine (93 rules)
POST /api/v1/intelligence/analyse   — Full StatMind Intelligence Engine
POST /api/v1/pca/analyze            — PCA with biplots
POST /api/v1/regression/logistic    — Logistic regression
POST /api/v1/attribute-charts/p     — p chart (fraction defective)
GET  /api/v1/health                 — Health check
```

Interactive API docs: `/docs`

---

## Statistical Standards

Results are computed per:

- **AIAG SPC Manual** 2nd Ed. — control charts, rational subgrouping
- **AIAG MSA** 4th Ed. — gauge R&R, linearity, bias
- **ISO 22514** — process capability for non-normal distributions
- **SEMI E10** — semiconductor equipment productivity
- **ASTM E2281** — Cpk confidence intervals (Bissell 1994)
- **IATF 16949:2016** — automotive quality management
- **AS9100D** — aerospace quality management
- **ISO 13485:2016** — medical devices quality management
- **USP <711>/<905>/<1216>** — pharmaceutical testing
- **IPC-A-610** — electronics assembly acceptance

---

## Project Structure

```
statmind/
  main.py                    ← FastAPI backend (2,897 lines, 145+ endpoints)
  capability.py              ← Cp/Cpk/Pp/Ppk with Welford variance
  control_charts.py          ← SPC charts with batch boundary detection
  normality.py               ← SW/AD/RJ with Shapiro sampling for n>5000
  gauge_rr.py                ← Two-way ANOVA GRR
  capa_rules_engine.py       ← CAPA pattern matching engine
  capa_database_r3.py        ← 93 CAPA rules (16 process families)
  statmind_intelligence.py   ← Intelligence Engine (Bayesian + TF-IDF + 8D)
  logistic_regression.py     ← Logistic + Stepwise regression (AIC/BIC)
  pca_advanced.py            ← PCA with biplots + scatter matrix
  attribute_charts.py        ← p/np/u/c attribute control charts
  weibull.py                 ← Weibull reliability analysis
  msa_linearity.py           ← MSA linearity and bias
  pdf_report.py              ← PDF report generation
  database.py                ← SQLAlchemy models (SQLite/PostgreSQL)
  requirements.txt           ← Python dependencies
  static/
    index.html               ← Single-page application (7,571 lines)
    landing.html             ← Marketing landing page
  tests/
    test_statistical_engines.py  ← 54 unit tests
```

---

## Deployment

Deployed on [Railway](https://railway.app) via auto-deploy from `main` branch.

```bash
git push origin main   # triggers Railway redeploy (~2 min)
```

---

## Topics

`statistics` `quality-engineering` `six-sigma` `spc` `process-capability` `gauge-rr` `capa` `doe` `minitab-alternative` `manufacturing` `fastapi` `python`

---

## License

MIT License. Statistical methods are standard academic references — see `standard_reference` fields in `capa_database_r3.py` for citations.

---

*StatMind v5.0 · Public Beta · © 2024–2026 StatMind*
