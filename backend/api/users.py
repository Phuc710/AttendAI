"""api/users.py — CRUD users (sinh viên + giáo viên + admin)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


class UserIn(BaseModel):
    user_code: str
    full_name: str
    role:      str = "student"   # student | teacher | admin
    email:     Optional[str] = None
    phone:     Optional[str] = None
    department: Optional[str] = None


class UserUpdate(BaseModel):
    user_code: Optional[str] = None
    full_name: Optional[str] = None
    role:      Optional[str] = None
    email:     Optional[str] = None
    phone:     Optional[str] = None
    department: Optional[str] = None


@router.get("")
def list_users(role: str = ""):
    with get_db() as conn:
        q = """
            SELECT u.*,
                   COUNT(e.id) as embed_count,
                   (SELECT e2.image_path FROM face_embeddings e2
                    WHERE e2.user_id = u.id ORDER BY e2.created_at LIMIT 1) as face_image
            FROM users u
            LEFT JOIN face_embeddings e ON e.user_id = u.id
            WHERE 1=1
        """
        p = []
        if role: q += " AND u.role=?"; p.append(role)
        rows = conn.execute(q + " GROUP BY u.id ORDER BY u.user_code", p).fetchall()
    return {"total": len(rows), "users": [dict(r) for r in rows]}


@router.post("", status_code=201)
def create_user(body: UserIn):
    with get_db() as conn:
        if conn.execute("SELECT id FROM users WHERE user_code=?", (body.user_code,)).fetchone():
            raise HTTPException(409, "Mã người dùng đã tồn tại")
        conn.execute(
            "INSERT INTO users (user_code, full_name, role, email, phone, department) VALUES (?,?,?,?,?,?)",
            (body.user_code, body.full_name, body.role, body.email, body.phone, body.department),
        )
        row = conn.execute("SELECT * FROM users WHERE user_code=?", (body.user_code,)).fetchone()
        # Thêm người dùng vào lớp mặc định 1 để index AI nhận diện tải tự động
        conn.execute("INSERT OR IGNORE INTO class_students (class_id, user_id) VALUES (1, ?)", (row["id"],))
    return dict(row)


@router.get("/{uid}")
def get_user(uid: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not row: raise HTTPException(404, "Không tìm thấy")
        emb_cnt = conn.execute("SELECT COUNT(*) FROM face_embeddings WHERE user_id=?", (uid,)).fetchone()[0]
        att_cnt = conn.execute(
            "SELECT COUNT(*) FROM attendance_logs WHERE user_id=? AND status='checked_in'", (uid,)
        ).fetchone()[0]
    data = dict(row)
    data["embed_count"] = emb_cnt
    data["att_count"]   = att_cnt
    return data


@router.put("/{uid}")
def update_user(uid: int, body: UserUpdate):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields: raise HTTPException(400, "Không có gì để cập nhật")
    sets = ", ".join(f"{k}=?" for k in fields)
    with get_db() as conn:
        conn.execute(f"UPDATE users SET {sets} WHERE id=?", [*fields.values(), uid])
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row: raise HTTPException(404, "Không tìm thấy")
    return dict(row)


@router.delete("/{uid}")
def delete_user(uid: int):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone():
            raise HTTPException(404, "Không tìm thấy")
        
        # Xóa các dữ liệu liên quan để tránh lỗi khóa ngoại
        conn.execute("DELETE FROM face_embeddings WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM attendance_logs WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM class_students WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
    return {"deleted": True}
