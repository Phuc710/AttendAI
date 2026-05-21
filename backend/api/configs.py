"""api/configs.py — Đọc/ghi system_configs (key-value)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_db

router = APIRouter(prefix="/api/configs", tags=["configs"])


class ConfigUpdate(BaseModel):
    value: str


@router.get("")
def list_configs():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM system_configs ORDER BY key").fetchall()
    return [dict(r) for r in rows]


@router.put("/{key}")
def update_config(key: str, body: ConfigUpdate):
    with get_db() as conn:
        if not conn.execute("SELECT key FROM system_configs WHERE key=?", (key,)).fetchone():
            raise HTTPException(404, f"Config key '{key}' không tồn tại")
        conn.execute(
            "UPDATE system_configs SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key=?",
            (body.value, key),
        )
        row = conn.execute("SELECT * FROM system_configs WHERE key=?", (key,)).fetchone()
    return dict(row)


@router.post("/system/reset")
def reset_database():
    """XÓA SẠCH DỮ LIỆU: Users, Classes, Logs, Embeddings."""
    with get_db() as conn:
        # Xóa theo thứ tự để tránh lỗi khóa ngoại
        conn.execute("DELETE FROM attendance_logs")
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM class_students")
        conn.execute("DELETE FROM classes")
        conn.execute("DELETE FROM face_embeddings")
        conn.execute("DELETE FROM users")
    return {"message": "Hệ thống đã được xóa sạch dữ liệu."}
