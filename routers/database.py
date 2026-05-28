import os
import logging
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, String, Float, DateTime, Integer, Text, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker

log = logging.getLogger("statmind.db")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./statmind_dev.db")

# Railway provides postgres:// — SQLAlchemy requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = "sqlite" in DATABASE_URL
_is_postgres = "postgresql" in DATABASE_URL

# Build engine with appropriate settings per backend
_engine_kwargs: dict = {}
if _is_sqlite:
    # SQLite: single-thread check needed for sync sessions
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL: connection pool for concurrent requests
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20
    _engine_kwargs["pool_pre_ping"] = True   # detects stale connections

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Use portable JSON type — works with both SQLite and PostgreSQL
# PostgreSQL will automatically use its native JSONB when available
_JSON = JSON


class ReportCache(Base):
    """Cached PDF reports — keyed by tenant + report ID."""
    __tablename__ = "report_cache"

    report_id  = Column(String,  primary_key=True, index=True)
    tenant_id  = Column(String,  index=True, nullable=False)
    pdf_bytes  = Column(Text,    nullable=False)   # Base64-encoded
    meta_data  = Column(_JSON,   nullable=True)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), index=True, nullable=True)


class StreamStore(Base):
    """Persistent MES live data streams."""
    __tablename__ = "stream_store"

    stream_id   = Column(String,  primary_key=True, index=True)
    tenant_id   = Column(String,  index=True, nullable=False)
    parameter   = Column(String,  nullable=False)
    usl         = Column(Float,   nullable=True)
    lsl         = Column(Float,   nullable=True)
    points      = Column(_JSON,   default=list)
    total_count = Column(Integer, default=0)
    updated_at  = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AnalysisSession(Base):
    """Persisted analysis results for session restore."""
    __tablename__ = "analysis_sessions"

    session_id   = Column(String,  primary_key=True, index=True)
    tenant_id    = Column(String,  index=True, nullable=False)
    filename     = Column(String,  nullable=True)
    process_type = Column(String,  nullable=True)
    parameter    = Column(String,  nullable=True)
    normality    = Column(_JSON,   nullable=True)
    capability   = Column(_JSON,   nullable=True)
    spc          = Column(_JSON,   nullable=True)
    grr          = Column(_JSON,   nullable=True)
    capa         = Column(_JSON,   nullable=True)
    created_at   = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


def init_db() -> bool:
    """
    Create all tables. Called explicitly from main.py startup,
    NOT at module import time — prevents crash if DB is unreachable.
    Returns True on success, False on failure (non-fatal for SQLite-less runs).
    """
    try:
        Base.metadata.create_all(bind=engine)
        log.info(f"Database tables initialised ({DATABASE_URL.split('://')[0]})")
        return True
    except Exception as exc:
        log.warning(f"DB init failed (non-fatal if no DB configured): {exc}")
        return False


def get_db():
    """FastAPI dependency: yields a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
