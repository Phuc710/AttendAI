"""api/attendance.py — Query log điểm danh (schema mới: user_id, session → class)."""

from fastapi import APIRouter, Query
from database import get_db

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


def _format_log(log_dict: dict) -> dict:
    for k in ["check_in_time", "check_out_time"]:
        val = log_dict.get(k)
        if val:
            val_str = str(val).replace(" ", "T")
            if not val_str.endswith("Z") and "+" not in val_str:
                val_str += "Z"
            log_dict[k] = val_str
    return log_dict


@router.get("/logs")
def get_logs(
    session_id: int | None = None,
    class_id:   int | None = None,
    status:     str | None = None,
    arrival_status: str | None = None,
    department: str | None = None,
    page:       int = Query(1, ge=1),
    limit:      int = Query(100, le=500),
):
    offset = (page - 1) * limit
    q = """
        SELECT l.id, l.check_in_time, l.check_out_time, l.confidence, l.status,
               l.arrival_status, l.check_in_method, l.snapshot_path,
               u.user_code, u.full_name, u.department,
               (SELECT e.image_path FROM face_embeddings e WHERE e.user_id = u.id ORDER BY e.created_at LIMIT 1) as face_image,
               g.group_name as class_name, g.description as subject_code,
               ses.session_code
        FROM attendance_logs l
        JOIN users u ON u.id = l.user_id
        JOIN sessions ses ON ses.id = l.session_id
        JOIN groups g ON g.id = ses.group_id
        WHERE 1=1
    """
    p = []
    if session_id: q += " AND l.session_id=?"; p.append(session_id)
    if status:     q += " AND l.status=?";     p.append(status)
    if class_id:   q += " AND ses.group_id=?"; p.append(class_id)
    if arrival_status: q += " AND l.arrival_status=?"; p.append(arrival_status)
    if department: q += " AND u.department=?"; p.append(department)
    q += " ORDER BY l.check_in_time DESC LIMIT ? OFFSET ?"
    p += [limit, offset]

    with get_db() as conn:
        rows  = conn.execute(q, p).fetchall()
        cq = """
            SELECT COUNT(*)
            FROM attendance_logs l
            JOIN users u ON u.id = l.user_id
            JOIN sessions ses ON ses.id = l.session_id
            WHERE 1=1
        """
        cp = []
        if session_id: cq += " AND l.session_id=?"; cp.append(session_id)
        if status:     cq += " AND l.status=?";     cp.append(status)
        if class_id:   cq += " AND ses.group_id=?"; cp.append(class_id)
        if arrival_status: cq += " AND l.arrival_status=?"; cp.append(arrival_status)
        if department: cq += " AND u.department=?"; cp.append(department)
        total = conn.execute(cq, cp).fetchone()[0]

    return {"total": total, "page": page, "logs": [_format_log(dict(r)) for r in rows]}


@router.get("/session/{session_id}")
def logs_by_session(session_id: int):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT l.id, l.check_in_time, l.check_out_time, l.confidence, l.status,
                   l.arrival_status, l.check_in_method, l.snapshot_path,
                   u.user_code, u.full_name
            FROM attendance_logs l
            JOIN users u ON u.id = l.user_id
            WHERE l.session_id=? AND l.status='checked_in'
            ORDER BY l.check_in_time
        """, (session_id,)).fetchall()
    return {"session_id": session_id, "total": len(rows), "logs": [_format_log(dict(r)) for r in rows]}


@router.get("/user/{user_id}")
def logs_by_user(user_id: int):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT l.id, l.check_in_time, l.check_out_time, l.confidence, l.status,
                   l.arrival_status, l.check_in_method,
                   ses.session_code, g.group_name as class_name, g.description as subject_code
            FROM attendance_logs l
            JOIN sessions ses ON ses.id = l.session_id
            JOIN groups g ON g.id = ses.group_id
            WHERE l.user_id=? AND l.status='checked_in'
            ORDER BY l.check_in_time DESC
        """, (user_id,)).fetchall()
    return {"user_id": user_id, "total": len(rows), "logs": [_format_log(dict(r)) for r in rows]}
