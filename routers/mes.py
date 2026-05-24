# routers/mes.py
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from schemas import MESStreamPayload
from database import get_db, StreamStore

router = APIRouter(prefix="/api/v1/mes", tags=["MES Livestream"])

@router.post("/ingest")
def ingest_mes_data(payload: MESStreamPayload, db: Session = Depends(get_db)):
    """
    Ingests live factory data securely into the persistent PostgreSQL database.
    """
    current_tenant = "tenant_alpha" # Hardcoded for Sprint 1
    
    # 1. Check if stream exists for this machine/parameter
    stream_id = f"{payload.machine_id}_{payload.parameter}"
    db_stream = db.query(StreamStore).filter_by(stream_id=stream_id, tenant_id=current_tenant).first()
    
    # 2. Create or Update
    if not db_stream:
        db_stream = StreamStore(
            stream_id=stream_id,
            tenant_id=current_tenant,
            parameter=payload.parameter,
            points=[{"value": payload.value, "timestamp": payload.timestamp}],
            total_count=1
        )
        db.add(db_stream)
    else:
        # Append new point and keep only last 200 to avoid JSONB bloat
        current_points = list(db_stream.points) if db_stream.points else []
        current_points.append({"value": payload.value, "timestamp": payload.timestamp})
        db_stream.points = current_points[-200:] 
        db_stream.total_count += 1

    db.commit()
    return {"status": "success", "stream_id": stream_id, "message": "Data secured to database"}