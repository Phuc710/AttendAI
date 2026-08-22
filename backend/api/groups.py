"""api/groups.py — CRUD groups + quản lý danh sách thành viên nhóm (group_members)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db

router = APIRouter(prefix="/api/groups", tags=["groups"])


class GroupIn(BaseModel):
    group_code:  str
    group_name:  str
    description: Optional[str] = None
    manager_id:  Optional[int] = None
    location:    Optional[str] = None


@router.get("")
def list_groups():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT g.*,
                   u.full_name as manager_name,
                   COUNT(DISTINCT gm.user_id) as member_count
            FROM groups g
            LEFT JOIN users u ON u.id = g.manager_id
            LEFT JOIN group_members gm ON gm.group_id = g.id
            GROUP BY g.id ORDER BY g.group_code
        """).fetchall()
    return {"total": len(rows), "groups": [dict(r) for r in rows]}


@router.post("", status_code=201)
def create_group(body: GroupIn):
    with get_db() as conn:
        if conn.execute("SELECT id FROM groups WHERE group_code=?", (body.group_code,)).fetchone():
            raise HTTPException(409, "Mã nhóm đã tồn tại")
        conn.execute(
            """INSERT INTO groups
               (group_code, group_name, description, manager_id, location)
               VALUES (?,?,?,?,?)""",
            (body.group_code, body.group_name, body.description,
             body.manager_id, body.location),
        )
        row = conn.execute("SELECT * FROM groups WHERE group_code=?", (body.group_code,)).fetchone()
    return dict(row)


@router.get("/{gid}")
def get_group(gid: int):
    with get_db() as conn:
        row = conn.execute("""
            SELECT g.*, u.full_name as manager_name
            FROM groups g LEFT JOIN users u ON u.id = g.manager_id
            WHERE g.id=?
        """, (gid,)).fetchone()
        if not row: raise HTTPException(404, "Không tìm thấy nhóm")
    return dict(row)


@router.delete("/{gid}")
def delete_group(gid: int):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM groups WHERE id=?", (gid,)).fetchone():
            raise HTTPException(404, "Không tìm thấy")
        
        # Lấy các session của nhóm
        sessions = conn.execute("SELECT id FROM sessions WHERE group_id=?", (gid,)).fetchall()
        session_ids = [s[0] for s in sessions]
        
        if session_ids:
            placeholders = ",".join("?" * len(session_ids))
            conn.execute(f"DELETE FROM attendance_logs WHERE session_id IN ({placeholders})", session_ids)
            conn.execute(f"DELETE FROM sessions WHERE group_id=?", (gid,))
            
        conn.execute("DELETE FROM group_members WHERE group_id=?", (gid,))
        conn.execute("DELETE FROM groups WHERE id=?", (gid,))
    return {"deleted": True}


# ── Quản lý danh sách thành viên (group_members) ──────────────────

@router.get("/{gid}/members")
def list_group_members(gid: int):
    """Lấy danh sách thành viên trong nhóm + embedding status."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT u.id, u.user_code, u.full_name,
                   COUNT(e.id) as embed_count,
                   gm.added_at
            FROM group_members gm
            JOIN users u ON u.id = gm.user_id
            LEFT JOIN face_embeddings e ON e.user_id = u.id
            WHERE gm.group_id=? AND u.is_deleted=0
            GROUP BY u.id ORDER BY u.user_code
        """, (gid,)).fetchall()
    return {"group_id": gid, "total": len(rows), "members": [dict(r) for r in rows]}


@router.post("/{gid}/members/{uid}", status_code=201)
def add_member_to_group(gid: int, uid: int):
    """Thêm nhân sự vào nhóm."""
    with get_db() as conn:
        if not conn.execute("SELECT id FROM groups WHERE id=?", (gid,)).fetchone():
            raise HTTPException(404, "Nhóm không tồn tại")
        if not conn.execute("SELECT id FROM users WHERE id=? AND is_deleted=0", (uid,)).fetchone():
            raise HTTPException(404, "Nhân sự không tồn tại")
        if conn.execute("SELECT id FROM group_members WHERE group_id=? AND user_id=?", (gid, uid)).fetchone():
            raise HTTPException(409, "Nhân sự đã có trong nhóm")
        conn.execute("INSERT INTO group_members (group_id, user_id) VALUES (?,?)", (gid, uid))
    return {"group_id": gid, "user_id": uid, "status": "added"}


@router.delete("/{gid}/members/{uid}")
def remove_member_from_group(gid: int, uid: int):
    """Xóa nhân sự khỏi nhóm."""
    with get_db() as conn:
        conn.execute("DELETE FROM group_members WHERE group_id=? AND user_id=?", (gid, uid))
    return {"group_id": gid, "user_id": uid, "status": "removed"}


@router.get("/{gid}/embeddings")
def get_group_embeddings(gid: int):
    """
    Load toàn bộ face_vector của nhóm lên — dùng khi Kiosk khởi động session.
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT e.user_id, e.embedding_json, u.full_name, u.user_code
            FROM face_embeddings e
            JOIN users u ON u.id = e.user_id
            WHERE u.is_deleted=0 AND e.user_id IN (
                SELECT user_id FROM group_members WHERE group_id=?
            )
            ORDER BY e.user_id, e.created_at DESC
        """, (gid,)).fetchall()
    return {"group_id": gid, "total": len(rows), "embeddings": [dict(r) for r in rows]}
