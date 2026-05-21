"""api/classes.py — CRUD classes + quản lý danh sách lớp (class_students)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db

router = APIRouter(prefix="/api/classes", tags=["classes"])


class ClassIn(BaseModel):
    class_code:   str
    class_name:   str
    subject_code: Optional[str] = None
    teacher_id:   Optional[int] = None
    room:         Optional[str] = None
    academic_year: Optional[str] = None
    semester:     Optional[str] = None


@router.get("")
def list_classes():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.*,
                   u.full_name as teacher_name,
                   COUNT(DISTINCT cs.user_id) as student_count
            FROM classes c
            LEFT JOIN users u ON u.id = c.teacher_id
            LEFT JOIN class_students cs ON cs.class_id = c.id
            GROUP BY c.id ORDER BY c.class_code
        """).fetchall()
    return {"total": len(rows), "classes": [dict(r) for r in rows]}


@router.post("", status_code=201)
def create_class(body: ClassIn):
    with get_db() as conn:
        if conn.execute("SELECT id FROM classes WHERE class_code=?", (body.class_code,)).fetchone():
            raise HTTPException(409, "Mã lớp đã tồn tại")
        conn.execute(
            """INSERT INTO classes
               (class_code, class_name, subject_code, teacher_id, room, academic_year, semester)
               VALUES (?,?,?,?,?,?,?)""",
            (body.class_code, body.class_name, body.subject_code,
             body.teacher_id, body.room, body.academic_year, body.semester),
        )
        row = conn.execute("SELECT * FROM classes WHERE class_code=?", (body.class_code,)).fetchone()
    return dict(row)


@router.get("/{cid}")
def get_class(cid: int):
    with get_db() as conn:
        row = conn.execute("""
            SELECT c.*, u.full_name as teacher_name
            FROM classes c LEFT JOIN users u ON u.id = c.teacher_id
            WHERE c.id=?
        """, (cid,)).fetchone()
        if not row: raise HTTPException(404, "Không tìm thấy lớp")
    return dict(row)


@router.delete("/{cid}")
def delete_class(cid: int):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM classes WHERE id=?", (cid,)).fetchone():
            raise HTTPException(404, "Không tìm thấy")
        
        # Lấy các session của lớp
        sessions = conn.execute("SELECT id FROM sessions WHERE class_id=?", (cid,)).fetchall()
        session_ids = [s[0] for s in sessions]
        
        if session_ids:
            placeholders = ",".join("?" * len(session_ids))
            conn.execute(f"DELETE FROM attendance_logs WHERE session_id IN ({placeholders})", session_ids)
            conn.execute(f"DELETE FROM sessions WHERE class_id=?", (cid,))
            
        conn.execute("DELETE FROM class_students WHERE class_id=?", (cid,))
        conn.execute("DELETE FROM classes WHERE id=?", (cid,))
    return {"deleted": True}


# ── Quản lý danh sách lớp (class_students) ──────────────────

@router.get("/{cid}/students")
def list_class_students(cid: int):
    """Lấy danh sách sinh viên trong lớp + embedding status."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT u.id, u.user_code, u.full_name, u.email,
                   COUNT(e.id) as embed_count,
                   cs.added_at
            FROM class_students cs
            JOIN users u ON u.id = cs.user_id
            LEFT JOIN face_embeddings e ON e.user_id = u.id
            WHERE cs.class_id=?
            GROUP BY u.id ORDER BY u.user_code
        """, (cid,)).fetchall()
    return {"class_id": cid, "total": len(rows), "students": [dict(r) for r in rows]}


@router.post("/{cid}/students/{uid}", status_code=201)
def add_student_to_class(cid: int, uid: int):
    """Giáo viên thêm sinh viên vào lớp."""
    with get_db() as conn:
        if not conn.execute("SELECT id FROM classes WHERE id=?", (cid,)).fetchone():
            raise HTTPException(404, "Lớp không tồn tại")
        if not conn.execute("SELECT id FROM users WHERE id=? AND role='student'", (uid,)).fetchone():
            raise HTTPException(404, "Sinh viên không tồn tại")
        if conn.execute("SELECT id FROM class_students WHERE class_id=? AND user_id=?", (cid, uid)).fetchone():
            raise HTTPException(409, "Sinh viên đã có trong lớp")
        conn.execute("INSERT INTO class_students (class_id, user_id) VALUES (?,?)", (cid, uid))
    return {"class_id": cid, "user_id": uid, "status": "added"}


@router.delete("/{cid}/students/{uid}")
def remove_student_from_class(cid: int, uid: int):
    """Xóa sinh viên khỏi lớp."""
    with get_db() as conn:
        conn.execute("DELETE FROM class_students WHERE class_id=? AND user_id=?", (cid, uid))
    return {"class_id": cid, "user_id": uid, "status": "removed"}


@router.get("/{cid}/embeddings")
def get_class_embeddings(cid: int):
    """
    Load toàn bộ face_vector của lớp lên — dùng khi Kiosk khởi động session.
    Chỉ lấy user_id và embedding_json để AI match trong RAM.
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT e.user_id, e.embedding_json, u.full_name, u.user_code
            FROM face_embeddings e
            JOIN users u ON u.id = e.user_id
            WHERE e.user_id IN (
                SELECT user_id FROM class_students WHERE class_id=?
            )
            ORDER BY e.user_id, e.created_at DESC
        """, (cid,)).fetchall()
    return {"class_id": cid, "total": len(rows), "embeddings": [dict(r) for r in rows]}
