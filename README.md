# StatMind — Process Statistics Platform

**Browser-based SPC, Capability Analysis, Gauge R&R, DOE, and CAPA for quality engineers.**

Live at [statmind.tech](https://statmind.tech) · [Open App](https://statmind.tech/app)

---

## What it does

StatMind replaces expensive desktop tools like Minitab ($6,000+/seat) with a free, browser-based statistics platform built specifically for manufacturing quality engineers.

| Analysis | Standards |
|---|---|
| Process Capability (Cp, Cpk, Pp, Ppk) | AIAG SPC 2nd Ed, ISO 22514 |
| SPC Control Charts (I-MR, Xbar-R, Xbar-S) | Western Electric + Nelson rules |
| Gauge R&R / MSA | AIAG MSA 4th Ed |
| Normality Tests (Shapiro-Wilk, Anderson-Darling, Ryan-Joiner) | ISO 5479 |
| CAPA Engine | 8D, IATF 16949, AS9100 |
| Design of Experiments (Full/Half/Quarter factorial, RSM) | — |
| PDF Report Generation | — |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Gunicorn |
| Statistics | SciPy, NumPy, Pandas, Statsmodels |
| Frontend | Vanilla JS, Chart.js 4.4 |
| Infrastructure | AWS EC2 t3.small, nginx, Docker |
| CI/CD | GitHub Actions → EC2 deploy |

---

## Local Development

### Prerequisites
- Python 3.12+
- pip

### Setup

```bash
git clone https://github.com/Prateek4803/statmind.git
cd statmind
pip install -r requirements.txt
uvicorn main:app --reload --port 8010
```

Open [http://localhost:8010/app](http://localhost:8010/app)

### Running tests

```bash
pytest tests/ -v
```

---

## Deployment

Deployed automatically via GitHub Actions on every push to `main`.

The workflow:
1. Runs Python syntax check and import validation
2. Runs statistical engine unit tests
3. Builds Docker image
4. Deploys to AWS EC2 via SSH
5. Health check confirms `/api/v1/health` returns 200

---

## Project Structure

```
statmind/
├── main.py                  # FastAPI app + all endpoints
├── capability.py            # Capability analysis engine
├── control_charts.py        # SPC chart engine
├── normality.py             # Normality test engine
├── gauge_rr.py              # Gauge R&R engine
├── email_capture.py         # Email capture endpoint
├── report_cache.py          # Thread-safe PDF cache with TTL
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── tests/
│   └── test_statistical_engines.py
└── static/
    ├── index.html           # Main app (single-page)
    ├── landing.html         # Landing page
    ├── privacy.html
    ├── terms.html
    ├── chart_config_patch.js
    └── ui_patch_v2.js
```

---

## API

Base URL: `https://statmind.tech`

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/health` | GET | Health check |
| `/api/v1/columns` | POST | Parse file, return column stats |
| `/api/v1/normality/analyze` | POST | Run normality tests |
| `/api/v1/capability/analyze` | POST | Run capability analysis |
| `/api/v1/spc/analyze` | POST | Build SPC control charts |
| `/api/v1/grr/analyze` | POST | Run Gauge R&R |
| `/api/v1/capa/v2/generate` | POST | Generate CAPA report |
| `/api/v1/report/generate` | POST | Generate PDF report |

Full API docs at `/docs` (Swagger UI).

---

## Industry Coverage

- **Semiconductor** — Etch, CMP, Litho, Diffusion (SEMI E10/E35)
- **Automotive** — PPAP, Control Plans (IATF 16949)
- **Aerospace** — Flight-critical, NDT (AS9100)
- **Medical Device** — Implant tolerances (ISO 13485 / FDA)
- **CMM / GD&T** — Dimensional inspection (ASME Y14.5)
- **General / Lab** — Any measurement system (ISO 17025)

---

## License

MIT — see [LICENSE](LICENSE)

---

## Contact

hello@statmind.tech
