"""api/sessions.py — Quản lý phiên học (sessions). Schema mới: class_id."""

from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_db
from services.attendance_service import reset_cache
from services import match_service as match_svc

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionStart(BaseModel):
    class_id:            int
    late_threshold_mins: int = 15


@router.post("/start", status_code=201)
def start_session(body: SessionStart):
    with get_db() as conn:
        # Kiểm tra lớp tồn tại
        cls = conn.execute("SELECT * FROM classes WHERE id=?", (body.class_id,)).fetchone()
        if not cls:
            raise HTTPException(404, "Lớp không tồn tại")

        # Kiểm tra session đang chạy
        active = conn.execute(
            "SELECT id, session_code FROM sessions WHERE status='active' LIMIT 1"
        ).fetchone()
        if active:
            raise HTTPException(409, {"error": "session_already_active", "session_code": active["session_code"]})

        code = f"{cls['class_code']}-{datetime.now().strftime('%Y%m%d-%H%M')}"
        conn.execute(
            """INSERT INTO sessions (session_code, class_id, late_threshold_mins)
               VALUES (?,?,?)""",
            (code, body.class_id, body.late_threshold_mins),
        )
        row = conn.execute("""
            SELECT s.*, c.class_name, c.subject_code, u.full_name as teacher_name
            FROM sessions s
            JOIN classes c ON c.id = s.class_id
            LEFT JOIN users u ON u.id = c.teacher_id
            WHERE s.session_code=?
        """, (code,)).fetchone()

    reset_cache()
    # Load class index vào FAISS RAM cho lớp này
    match_svc.load_class_index(body.class_id)
    return dict(row)


@router.post("/end")
def end_session():
    with get_db() as conn:
        session = conn.execute(
            "SELECT * FROM sessions WHERE status='active' LIMIT 1"
        ).fetchone()
        if not session: raise HTTPException(404, "Không có session đang chạy")

        conn.execute(
            "UPDATE sessions SET status='closed', ended_at=CURRENT_TIMESTAMP WHERE id=?",
            (session["id"],),
        )
        total = conn.execute(
            "SELECT COUNT(*) FROM attendance_logs WHERE session_id=? AND status='checked_in'",
            (session["id"],),
        ).fetchone()[0]

    reset_cache()
    match_svc.clear_class_index()
    return {
        "session_id":    session["id"],
        "session_code":  session["session_code"],
        "status":        "closed",
        "ended_at":      datetime.now().isoformat(),
        "total_checked": total,
    }


@router.get("/active")
def get_active():
    with get_db() as conn:
        row = conn.execute("""
            SELECT s.*,
                   c.class_name, c.subject_code, c.room,
                   u.full_name as teacher_name,
                   COUNT(l.id) as total_checked,
                   SUM(CASE WHEN l.arrival_status='late' THEN 1 ELSE 0 END) as total_late,
                   (SELECT COUNT(*) FROM class_students cs WHERE cs.class_id = s.class_id) as total_students
            FROM sessions s
            JOIN classes c ON c.id = s.class_id
            LEFT JOIN users u ON u.id = c.teacher_id
            LEFT JOIN attendance_logs l ON l.session_id=s.id AND l.status='checked_in'
            WHERE s.status='active'
            GROUP BY s.id LIMIT 1
        """).fetchone()
    if not row:
        return None
    return dict(row)


@router.get("")
def list_sessions(limit: int = 30):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT s.*,
                   c.class_name, c.subject_code, c.room,
                   u.full_name as teacher_name,
                   COUNT(l.id) as total_checked,
                   SUM(CASE WHEN l.arrival_status='late' THEN 1 ELSE 0 END) as total_late,
                   ROUND(AVG(l.confidence),3) as avg_conf
            FROM sessions s
            JOIN classes c ON c.id = s.class_id
            LEFT JOIN users u ON u.id = c.teacher_id
            LEFT JOIN attendance_logs l ON l.session_id=s.id AND l.status='checked_in'
            GROUP BY s.id ORDER BY s.started_at DESC LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/{sid}/logs")
def session_logs(sid: int):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT l.id, l.check_in_time, l.confidence, l.status,
                   l.arrival_status, l.check_in_method, l.snapshot_path,
                   u.user_code, u.full_name
            FROM attendance_logs l
            JOIN users u ON u.id = l.user_id
            WHERE l.session_id=?
            ORDER BY l.check_in_time
        """, (sid,)).fetchall()
    return {"session_id": sid, "total": len(rows), "logs": [dict(r) for r in rows]}
