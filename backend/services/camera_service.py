"""camera_service.py — Camera thread: đọc frame → AI → WS push."""

import logging
import queue
import threading
import time
import uuid
import cv2
import numpy as np

import services.face_service    as face_svc
import services.match_service   as match_svc
import services.attendance_service as att_svc
from services.ws_service import broadcaster
from config import (CAMERA_SOURCE, CAMERA_WIDTH, CAMERA_HEIGHT,
                    CAMERA_FPS, FRAME_SKIP, SAVE_UNKNOWN, UNKNOWN_DIR)

log = logging.getLogger("camera_service")

# ─── State ────────────────────────────────────────────────

_state = {
    "running":   False,
    "cap":       None,
    "fps":       0.0,
    "frame_raw": None,          # bytes JPEG frame mới nhất (không có bbox)
    "lock":      threading.Lock(),
    "error":     "",
}

_frame_queue: queue.Queue = queue.Queue(maxsize=2)


# ─── Camera reader thread ─────────────────────────────────

def _reader_thread():
    cap   = _state["cap"]
    count = 0
    while _state["running"]:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue
        count += 1

        # Lưu frame raw (MJPEG cho browser)
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        with _state["lock"]:
            _state["frame_raw"] = buf.tobytes()

        # Chỉ đẩy vào queue mỗi FRAME_SKIP frame
        if count % FRAME_SKIP != 0:
            continue
        if _frame_queue.full():
            try:
                _frame_queue.get_nowait()
            except queue.Empty:
                pass
        _frame_queue.put(frame)


# ─── AI worker thread ─────────────────────────────────────

def _ai_worker():
    fps_timer  = time.time()
    fps_count  = 0

    while _state["running"]:
        try:
            frame = _frame_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        t0 = time.time()
        faces = face_svc.detect_and_embed(frame)
        fps_count += 1

        # Gửi live bboxes về frontend ngay sau khi detect
        live_faces = [{"bbox": f["bbox"]} for f in faces]
        faces_to_broadcast = []

        for face in faces:
            emb   = face["embedding"]
            bbox  = face["bbox"]
            user, score = match_svc.match(emb)
            
            label = "Unknown"
            if user:
                label = user["user_code"]
                result = att_svc.handle(
                    user_id=user["user_id"],
                    confidence=score,
                    bbox=bbox,
                    frame=frame,
                )
                status = result["status"]
                if status == "checked_in":
                    broadcaster.push_checkin_success(user, score, bbox, result.get("log_id", 0), result.get("snapshot_path", ""), result.get("arrival_status", "on_time"))
                elif status == "already_checked_in":
                    broadcaster.push_already_checked(user, bbox, result.get("arrival_status", "on_time"))
            else:
                if SAVE_UNKNOWN:
                    _save_unknown(face_svc.crop_face(frame, bbox))
                broadcaster.push_unknown(score, bbox)
            
            faces_to_broadcast.append({"bbox": bbox, "name": label})

        # Gửi toàn bộ khung hình kèm tên về Kiosk
        broadcaster.push_live_faces(faces_to_broadcast)

        # FPS
        processing_ms = int((time.time() - t0) * 1000)
        elapsed = time.time() - fps_timer
        if elapsed >= 1.0:
            _state["fps"] = round(fps_count / elapsed, 1)
            fps_count  = 0
            fps_timer  = time.time()
            broadcaster.push_frame_stats(_state["fps"], len(faces), processing_ms)


def _save_unknown(crop: np.ndarray):
    if crop.size == 0:
        return
    path = UNKNOWN_DIR / f"unk_{uuid.uuid4().hex[:8]}.jpg"
    _, buf = cv2.imencode(".jpg", crop)
    path.write_bytes(buf.tobytes())


# ─── Public API ───────────────────────────────────────────

def start(source=None):
    if _state["running"]:
        return False, "Đang chạy rồi"

    cam_src = source or CAMERA_SOURCE
    try:
        cam_idx = int(cam_src)
        cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)
    except ValueError:
        cap = cv2.VideoCapture(cam_src)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

    if not cap.isOpened():
        return False, "Không mở được camera"

    _state["cap"]     = cap
    _state["running"] = True
    _state["error"]   = ""

    threading.Thread(target=_reader_thread, daemon=True).start()
    threading.Thread(target=_ai_worker,     daemon=True).start()
    log.info(f"Camera started: {cam_src}")
    return True, "OK"


def stop():
    _state["running"] = False
    cap = _state.get("cap")
    if cap:
        cap.release()
        _state["cap"] = None
    broadcaster.push_camera_offline("Camera stopped")
    log.info("Camera stopped")


def status() -> dict:
    return {
        "connected":   _state["running"],
        "source":      str(CAMERA_SOURCE),
        "fps":         _state["fps"],
        "resolution":  f"{CAMERA_WIDTH}x{CAMERA_HEIGHT}",
        "error":       _state["error"],
    }


def get_frame_bytes() -> bytes | None:
    with _state["lock"]:
        return _state["frame_raw"]


def mjpeg_generator():
    """Generator cho MJPEG stream (dùng trong StreamingResponse)."""
    while _state["running"]:
        frame = get_frame_bytes()
        if frame:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame +
                b"\r\n"
            )
        time.sleep(0.033)
