"""
StatMind — main.py  (router-split refactor)

HOW TO ADOPT
============
1. Drop the new routers/ directory next to main.py
2. Replace the inline endpoint blocks with the include_router calls below
3. The existing @app.get / @app.post decorators for capability + SPC can be
   DELETED once their routers are included — FastAPI will use the routers.

This file shows ONLY the wiring pattern; the rest of main.py stays unchanged.

BEFORE (2,897-line monolith):
    @app.post("/api/v1/capability/analyze")
    async def capability_analyze(file: UploadFile, ...):
        # 80 lines of inline logic
        ...

AFTER (clean router split):
    app.include_router(capability_router.router)
    app.include_router(spc_router.router)
    # etc.

MIGRATION CHECKLIST
===================
[ ] pip install fastapi uvicorn gunicorn  (already done)
[ ] Copy routers/ directory to repo root
[ ] Add the include_router lines below to main.py __init__ block
[ ] Run: pytest tests/test_statistical_engines.py -v
[ ] Remove old inline endpoints one by one
[ ] git push → CI/CD auto-deploys

"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# New modular routers
from routers.capability_router import router as capability_router
from routers.spc_router import router as spc_router

app = FastAPI(
    title="StatMind API",
    description="Process Statistics Engine for Manufacturing — v5.0",
    version="5.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS (keep existing policy) ───────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(capability_router)
app.include_router(spc_router)

# TODO: add as each router is extracted from main.py
# from routers.grr_router      import router as grr_router
# from routers.doe_router      import router as doe_router
# from routers.capa_router     import router as capa_router
# from routers.regression_router import router as regression_router
# app.include_router(grr_router)
# app.include_router(doe_router)
# app.include_router(capa_router)
# app.include_router(regression_router)
