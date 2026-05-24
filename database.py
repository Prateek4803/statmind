import os
import logging
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB, BYTEA
from sqlalchemy.orm import declarative_base, sessionmaker

log = logging.getLogger("statmind.db")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./statmind_dev.db")

# Ensure Railway's postgres:// is converted to postgresql:// for SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    # check_same_thread is only for SQLite local dev
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ── Enterprise Schema Definitions ──────────────────────────────────────────────

class ReportCache(Base):
    __tablename__ = "report_cache"
    
    report_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False) # CRITICAL for B2B
    pdf_bytes = Column(BYTEA, nullable=False)
    meta_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), index=True)

class StreamStore(Base):
    __tablename__ = "stream_store"
    
    stream_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    parameter = Column(String, nullable=False)
    usl = Column(Float, nullable=True)
    lsl = Column(Float, nullable=True)
    points = Column(JSONB, default=[])
    total_count = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"
    
    session_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    filename = Column(String)
    process_type = Column(String)
    parameter = Column(String)
    normality = Column(JSONB)
    capability = Column(JSONB)
    spc = Column(JSONB)
    grr = Column(JSONB)
    capa = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

# Bootstrap the tables (In the future, use Alembic for this)
Base.metadata.create_all(bind=engine)

# Dependency to inject DB sessions into FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()