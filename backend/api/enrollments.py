"""api/enrollments.py — Đăng ký khuôn mặt (user_id thay student_id)."""

import json
import io
from fastapi import APIRouter, HTTPException, UploadFile, File
import cv2
import numpy as np
import uuid

from database import get_db
from services.face_service import embed_image
from services.match_service import reload_index
from config import ENROLLED_DIR

router = APIRouter(prefix="/api/enrollments", tags=["enrollments"])


@router.post("/{user_id}", status_code=201)
async def enroll(user_id: int, image: UploadFile = File(...)):
    with get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id=? AND is_deleted=0", (user_id,)).fetchone()
    if not user:
        raise HTTPException(404, "User not found")

    raw = await image.read()
    arr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Invalid image")

    emb, det_score, face_count = embed_image(img)
    if face_count == 0:
        raise HTTPException(422, detail="Không phát hiện khuôn mặt trong ảnh. Hãy thử ảnh khác rõ mặt hơn.")
    if det_score < 0.3:
        raise HTTPException(422, detail=f"Chất lượng ảnh quá thấp ({det_score:.2f}). Cần ảnh sáng, rõ nét hơn.")

    # Kiểm tra trùng mặt trên hệ thống
    from services.match_service import match
    matched_user, match_score = match(emb)
    if matched_user and matched_user["user_id"] != user_id:
        raise HTTPException(
            422,
            detail=f"Khuôn mặt này đã được đăng ký bởi nhân viên khác (Mã: {matched_user['user_code']}, Tên: {matched_user['full_name']})!"
        )

    fname = f"{user_id}_{uuid.uuid4().hex[:8]}.jpg"
    path  = ENROLLED_DIR / fname
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    path.write_bytes(buf.tobytes())

    emb_json = json.dumps(emb.tolist())
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO face_embeddings (user_id, embedding_json, image_path, quality_score) VALUES (?,?,?,?)",
            (user_id, emb_json, str(path), det_score),
        )
        emb_id = cur.lastrowid

    reload_index()

    return {
        "embedding_id":  emb_id,
        "user_id":       user_id,
        "quality_score": round(det_score, 4),
        "image_path":    str(path),
        "message":       "Enrollment success",
    }


@router.get("/{user_id}")
def get_enrollments(user_id: int):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, quality_score, image_path, created_at FROM face_embeddings WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return {"user_id": user_id, "embeddings": [dict(r) for r in rows]}


@router.delete("/{user_id}")
def delete_enrollments(user_id: int):
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM face_embeddings WHERE user_id=?", (user_id,)).fetchone()[0]
        conn.execute("DELETE FROM face_embeddings WHERE user_id=?", (user_id,))
    reload_index()
    return {"deleted": count}
