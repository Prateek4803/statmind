# StatMind — Process Statistics Engine

A Minitab-style statistical analysis tool for semiconductor fabs.

## What it does

Upload process data (CSV/Excel) → full statistical analysis → downloadable PDF report

| Session | Module | What it computes |
|---------|--------|-----------------|
| 1 | Normality | Shapiro-Wilk, Anderson-Darling, Ryan-Joiner |
| 2 | Capability | Cp, Cpk, Pp, Ppk, confidence intervals, PPM |
| 3 | Control Charts | I-MR / Xbar-R / Xbar-S, Western Electric + Nelson rules |
| 4 | Gauge R&R | Two-way ANOVA, %GRR, ndc, variance decomposition |
| 5 | CAPA Engine | Rule-based fault matching (Etch/CMP/Litho/Diffusion) |
| 6 | PDF Report | Professional report with all charts embedded |

## Running locally

```powershell
# Windows (PowerShell)
cd C:\Users\ASUS\Downloads\StatMind
.venv\Scripts\activate
uvicorn main:app --port 8010

# Open in browser
# Option A: double-click statmind_s6.html
# Option B: python -m http.server 8020 → http://localhost:8020/statmind_s6.html
# Option C (self-contained): copy statmind_s6.html to static/index.html, then http://localhost:8010
```

## File structure

```
StatMind/
  main.py               ← single production entry point (Sessions 1-6)
  normality.py          ← Session 1: SW, AD, RJ tests
  capability.py         ← Session 2: Cp/Cpk/Pp/Ppk
  control_charts.py     ← Session 3: I-MR, Xbar-R, Xbar-S, WE+Nelson rules
  gauge_rr.py           ← Session 4: Two-way ANOVA GRR
  capa_database.py      ← Session 5: 21 semiconductor CAPA rules
  capa_rules_engine.py  ← Session 5: Pattern matching engine
  pdf_report.py         ← Session 6: ReportLab PDF generator
  statmind_s6.html      ← Frontend dashboard (all 6 sessions)
  requirements.txt      ← Python dependencies
  Procfile              ← Railway deployment
  render.yaml           ← Render deployment
  railway.json          ← Railway config
```

## Deploying to Railway (recommended)

1. Create a free account at railway.app
2. New Project → Deploy from GitHub (push StatMind folder to a GitHub repo first)
3. Railway auto-detects Python, installs requirements.txt, starts with Procfile
4. Copy the generated URL (e.g. https://statmind-production.up.railway.app)
5. Update `API` in statmind_s6.html or use the self-contained mode (static/index.html)

## Deploying to Render

1. Create account at render.com
2. New → Web Service → Connect GitHub repo
3. Render reads render.yaml automatically
4. Free tier available (spins down after 15 min idle)

## GRR CSV format

```csv
Part,Operator,Measurement
P01,Op A,2.0032
P01,Op A,2.0011
P01,Op B,2.0078
...
```

## CAPA rule coverage

- **Etch**: CD centering, etch rate drift, bimodal uniformity, high GRR, stratification
- **CMP**: removal rate offset, WIWNU spread, pad glazing trend, non-normal thickness
- **Lithography**: CD low Cpk, overlay error, focus gradient, step-change events
- **Diffusion**: Rs furnace offset, junction depth non-uniformity, heating element aging, GRR
- **General**: Cpk<1.0, GRR>30%, step change (any process), ndc<5
