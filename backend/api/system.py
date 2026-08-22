"""api/system.py — API quản lý nhật ký hệ thống."""

from fastapi import APIRouter, Query
from database import get_db

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/logs")
def get_system_logs(
    event_type: str | None = None,
    page:       int = Query(1, ge=1),
    limit:      int = Query(100, le=500),
):
    offset = (page - 1) * limit
    q = "SELECT * FROM system_logs WHERE 1=1"
    p = []
    
    if event_type:
        q += " AND event_type=?"
        p.append(event_type)
        
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    p += [limit, offset]
    
    with get_db() as conn:
        rows = conn.execute(q, p).fetchall()
        cq = "SELECT COUNT(*) FROM system_logs WHERE 1=1"
        cp = []
        if event_type:
            cq += " AND event_type=?"
            cp.append(event_type)
        total = conn.execute(cq, cp).fetchone()[0]
        
    return {"total": total, "page": page, "logs": [dict(r) for r in rows]}
