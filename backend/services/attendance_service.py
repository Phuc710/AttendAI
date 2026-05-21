"""attendance_service.py — Ghi điểm danh + 3 lớp chống duplicate.

Schema mới: bảng sessions (class_id), users (thay students), attendance_logs (user_id).
"""

import logging
import time
import uuid
import cv2
import numpy as np
from datetime import datetime
from database import get_db
from config import DUPLICATE_TIME_WINDOW, SAVE_SNAPSHOT, SNAPSHOTS_DIR

log = logging.getLogger("attendance_service")

# ─── Tầng 1: In-memory time window ────────────────────────
_recent: dict[int, float] = {}


def reset_cache():
    global _recent
    _recent = {}


def _in_time_window(user_id: int) -> bool:
    last = _recent.get(user_id)
    return last is not None and (time.time() - last) < DUPLICATE_TIME_WINDOW


def _mark_recent(user_id: int):
    _recent[user_id] = time.time()


# ─── Tầng 2: DB session check ─────────────────────────────

def _get_log_in_session(session_id: int, user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("""
            SELECT id FROM attendance_logs
            WHERE session_id=? AND user_id=?
            LIMIT 1
        """, (session_id, user_id)).fetchone()
    return dict(row) if row else None


# ─── Active session ───────────────────────────────────────

def get_active_session() -> dict | None:
    with get_db() as conn:
        row = conn.execute("""
            SELECT s.*, c.class_name, c.subject_code,
                   u.full_name as teacher_name
            FROM sessions s
            JOIN classes c ON c.id = s.class_id
            LEFT JOIN users u ON u.id = c.teacher_id
            WHERE s.status='active'
            ORDER BY s.started_at DESC LIMIT 1
        """).fetchone()
    return dict(row) if row else None


def _calc_arrival(session: dict) -> str:
    try:
        started = datetime.fromisoformat(session["started_at"])
        diff = (datetime.now() - started).total_seconds() / 60
        return "late" if diff > session.get("late_threshold_mins", 15) else "on_time"
    except Exception:
        return "on_time"


# ─── Lưu ảnh snapshot khi điểm danh ──────────────────────

def _save_snapshot(frame: np.ndarray, user_id: int) -> str:
    if not SAVE_SNAPSHOT:
        return ""
    try:
        fname = f"snap_{user_id}_{uuid.uuid4().hex[:8]}.jpg"
        path  = SNAPSHOTS_DIR / fname
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        path.write_bytes(buf.tobytes())
        return str(path)
    except Exception:
        return ""


# ─── Main handler (AI worker gọi sau khi match thành công) ─

def handle(
    user_id: int,
    confidence: float,
    bbox: dict,
    frame: np.ndarray,
) -> dict:
    """
    Xử lý 1 khuôn mặt đã match.
    Trả về { status, message, log_id?, arrival_status? }
    """
    # Tầng 1 — in-memory
    if _in_time_window(user_id):
        return {"status": "duplicate_ignored", "message": "Đã điểm danh gần đây"}

    session = get_active_session()
    if session is None:
        return {"status": "no_active_session", "message": "Chưa có buổi học đang mở"}

    # Tầng 2 — DB check
    # Tầng 2 — DB check: Có trong DB rồi -> Check-OUT. Chưa có -> Check-IN
    existing_log = _get_log_in_session(session["id"], user_id)
    snapshot_path = _save_snapshot(frame, user_id)

    if existing_log:
        # Nếu đã có trong DB rồi thì KHÔNG lưu thêm, KHÔNG làm gì cả
        return {
            "status": "already_checked_in",
            "log_id": existing_log["id"]
        }

    # ─── CHƯA CÓ TRONG DB -> GHI NHẬN CHECK-IN ───
    arrival = _calc_arrival(session)
    try:
        with get_db() as conn:
            cur = conn.execute("""
                INSERT INTO attendance_logs
                    (session_id, user_id, confidence,
                     check_in_method, arrival_status, snapshot_path, status)
                VALUES (?,?,?, 'face',?,?, 'checked_in')
            """, (session["id"], user_id, confidence, arrival, snapshot_path))
            log_id = cur.lastrowid
    except Exception as e:
        log.error(f"DB error on check-in: {e}")
        return {"status": "db_error", "message": str(e)}

    _mark_recent(user_id)
    log.info(f"✓ checked_in: user={user_id} conf={confidence:.3f} arrival={arrival}")
    return {
        "status":         "checked_in",
        "message":        "Check-in thành công",
        "log_id":         log_id,
        "arrival_status": arrival,
        "snapshot_path":  snapshot_path,
    }


def manual_checkin(user_id: int, session_id: int) -> dict:
    """Điểm danh thủ công bởi giáo viên."""
    if _get_log_in_session(session_id, user_id):
        return {"status": "already_checked_in"}

    session_row = get_active_session()
    arrival = _calc_arrival(session_row) if session_row else "on_time"

    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO attendance_logs
                (session_id, user_id, confidence, check_in_method, arrival_status, status)
            VALUES (?,?, 1.0, 'manual', ?, 'checked_in')
        """, (session_id, user_id, arrival))
        log_id = cur.lastrowid

    _mark_recent(user_id)
    return {"status": "checked_in", "log_id": log_id, "arrival_status": arrival}
