"""api/users.py — CRUD users (sinh viên + giáo viên + admin)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db, log_event

router = APIRouter(prefix="/api/users", tags=["users"])


class UserIn(BaseModel):
    user_code: str
    full_name: str
    department: Optional[str] = None


class UserUpdate(BaseModel):
    user_code: Optional[str] = None
    full_name: Optional[str] = None
    department: Optional[str] = None


@router.get("")
def list_users():
    with get_db() as conn:
        q = """
            SELECT u.*,
                   COUNT(e.id) as embed_count,
                   (SELECT e2.image_path FROM face_embeddings e2
                    WHERE e2.user_id = u.id ORDER BY e2.created_at LIMIT 1) as face_image
            FROM users u
            LEFT JOIN face_embeddings e ON e.user_id = u.id
            WHERE u.is_deleted = 0
            GROUP BY u.id ORDER BY u.user_code
        """
        rows = conn.execute(q).fetchall()
    return {"total": len(rows), "users": [dict(r) for r in rows]}


@router.post("", status_code=201)
def create_user(body: UserIn):
    with get_db() as conn:
        existing = conn.execute("SELECT id, is_deleted FROM users WHERE user_code=?", (body.user_code,)).fetchone()
        if existing:
            if existing["is_deleted"] == 0:
                raise HTTPException(409, "Mã người dùng đã tồn tại")
            else:
                conn.execute(
                    "UPDATE users SET is_deleted=0, full_name=?, department=? WHERE id=?",
                    (body.full_name, body.department, existing["id"])
                )
                row = conn.execute("SELECT * FROM users WHERE id=?", (existing["id"],)).fetchone()
                log_event("register", f"Đăng ký lại nhân sự: {body.full_name} ({body.user_code})", f"Phòng ban: {body.department}")
                return dict(row)

        conn.execute(
            "INSERT INTO users (user_code, full_name, department, is_deleted) VALUES (?,?,?, 0)",
            (body.user_code, body.full_name, body.department),
        )
        row = conn.execute("SELECT * FROM users WHERE user_code=?", (body.user_code,)).fetchone()
        conn.execute("INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (1, ?)", (row["id"],))
    log_event("register", f"Đăng ký nhân sự thành công: {body.full_name} ({body.user_code})", f"Phòng ban: {body.department}")
    return dict(row)


@router.get("/check/{user_code}")
def check_user_code(user_code: str):
    with get_db() as conn:
        row = conn.execute("SELECT id, full_name, department FROM users WHERE user_code=? AND is_deleted=0", (user_code,)).fetchone()
    if row:
        return {"exists": True, "user": dict(row)}
    return {"exists": False, "user": None}


@router.get("/{uid}")
def get_user(uid: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=? AND is_deleted=0", (uid,)).fetchone()
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
        conn.execute(f"UPDATE users SET {sets} WHERE id=? AND is_deleted=0", [*fields.values(), uid])
        row = conn.execute("SELECT * FROM users WHERE id=? AND is_deleted=0", (uid,)).fetchone()
    if not row: raise HTTPException(404, "Không tìm thấy")
    
    from services.match_service import reload_index
    reload_index()
    
    return dict(row)


@router.delete("/{uid}")
def delete_user(uid: int):
    with get_db() as conn:
        user = conn.execute("SELECT user_code, full_name FROM users WHERE id=? AND is_deleted=0", (uid,)).fetchone()
        if not user: raise HTTPException(404, "Không tìm thấy")
        conn.execute("DELETE FROM face_embeddings WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM group_members WHERE user_id=?", (uid,))
        conn.execute("UPDATE users SET is_deleted=1 WHERE id=?", (uid,))
    log_event("register", f"Xóa nhân sự thành công (Giữ lịch sử): {user['full_name']} ({user['user_code']})", f"User ID: {uid}")
    
    from services.match_service import reload_index
    reload_index()
    
    return {"deleted": True}
