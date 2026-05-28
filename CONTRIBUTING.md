# Contributing to StatMind

Thank you for your interest in contributing to StatMind — a free, browser-based process statistics platform for quality engineers.

## Getting Started

### Prerequisites
- Python 3.12+
- Git

### Local Setup

```bash
git clone https://github.com/Prateek4803/statmind.git
cd statmind
pip install -r requirements.txt
uvicorn main:app --reload --port 8010
```

Open http://localhost:8010/app

### Running Tests

```bash
pip install pytest
pytest tests/ -v
```

All PRs must pass the full test suite before merging.

## How to Contribute

### Reporting Bugs
Open an issue with:
- What you did
- What you expected
- What actually happened
- Browser + OS

### Suggesting Features
Open an issue tagged `enhancement`. For statistical features, please cite the relevant standard (AIAG, ISO, SEMI, etc.).

### Submitting Code

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Write tests for any new statistical logic
4. Run `pytest tests/ -v` — all tests must pass
5. Open a PR against `main`

## Code Standards

- **Statistical accuracy first** — cite the formula source in comments (e.g. "Bissell 1990 CI formula")
- **No new endpoints without tests** — even a smoke test
- **No binary files** — never commit `.zip`, `.db`, or compiled files
- **Never commit secrets** — API keys, passwords, tokens go in env vars only

## Project Structure

```
statmind/
├── main.py              # FastAPI app — all endpoints
├── capability.py        # Cp/Cpk/Pp/Ppk engine
├── normality.py         # Shapiro-Wilk, Anderson-Darling, Ryan-Joiner
├── control_charts.py    # I-MR, Xbar-R, Xbar-S, CUSUM, EWMA
├── gauge_rr.py          # Gauge R&R / MSA
├── auth.py              # Magic link authentication
├── ppap_generator.py    # PPAP PDF generator
├── report_cache.py      # Thread-safe PDF cache with TTL
├── requirements.txt
├── Dockerfile
├── tests/
│   ├── test_capability.py
│   └── test_statistical_engines.py
└── static/
    ├── index.html       # Main app
    ├── landing.html     # Landing page
    └── *.js             # Patch files
```

## Statistical Standards

StatMind targets compliance with:
- **AIAG SPC 2nd Ed** — control chart constants, rules
- **AIAG MSA 4th Ed** — Gauge R&R acceptance criteria
- **ISO 22514** — process capability
- **SEMI E10/E35** — semiconductor equipment metrics
- **IATF 16949** — automotive quality management

If you find a calculation error, please open an issue immediately with the correct formula and source.

## Contact

hello@statmind.tech
