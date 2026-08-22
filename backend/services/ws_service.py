"""ws_service.py — WebSocket broadcaster (fan-out to all clients)."""

import asyncio
import json
import logging
from datetime import datetime
from fastapi import WebSocket

log = logging.getLogger("ws_service")


class WSBroadcaster:
    def __init__(self):
        self._clients: list[WebSocket] = []
        self._loop = None

    async def connect(self, ws: WebSocket):
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        await ws.accept()
        self._clients.append(ws)
        log.info(f"WS client connected. Total: {len(self._clients)}")
        try:
            while True:
                await ws.receive_text()  # giữ kết nối, bỏ qua msg từ client
        except Exception:
            pass
        finally:
            # Dùng try/except thay vì remove() để tránh ValueError khi đã bị xóa bởi broadcast()
            try:
                self._clients.remove(ws)
            except ValueError:
                pass
            log.info(f"WS client disconnected. Total: {len(self._clients)}")

    async def broadcast(self, payload: dict):
        if not self._clients:
            return
        msg = json.dumps(payload, ensure_ascii=False, default=str)
        dead = []
        for ws in list(self._clients):  # copy list để tránh concurrent modification
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self._clients.remove(ws)
            except ValueError:
                pass

    def push(self, payload: dict):
        """Gọi từ thread đồng bộ (AI worker) — schedule vào event loop."""
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(payload), self._loop)
        except Exception as e:
            log.warning(f"WS push error: {e}")

    # ─── Helpers ───────────────────────────────────────────────

    def push_checkin_success(self, user: dict, confidence: float, bbox: dict, log_id: int, snapshot_path: str = "", arrival_status: str = "on_time"):
        self.push({
            "event":        "checkin_success",
            "user_id":      user.get("user_id"),
            "user_code":    user.get("user_code"),
            "student_code": user.get("user_code"),   # alias for kiosk.js compat
            "full_name":    user.get("full_name", "Unknown"),
            "department":   user.get("department", "Nhân sự"),
            "confidence":   round(confidence, 4),
            "bbox":         bbox,
            "log_id":       log_id,
            "snapshot_path": snapshot_path,
            "face_image":    user.get("face_image"),
            "checkin_time": datetime.utcnow().isoformat() + "Z",
            "arrival_status": arrival_status,
        })

    def push_already_checked(self, student: dict, bbox: dict = None, arrival_status: str = "on_time"):
        self.push({
            "event":      "already_checked_in",
            "user_id":    student.get("user_id"),
            "user_code":  student.get("user_code"),
            "full_name":  student.get("full_name", "Unknown"),
            "department":  student.get("department", "Nhân sự"),
            "face_image":  student.get("face_image"),
            "bbox":       bbox,
            "checkin_time": datetime.utcnow().isoformat() + "Z",
            "arrival_status": arrival_status,
        })

    def push_unknown(self, confidence: float, bbox: dict):
        self.push({
            "event":      "unknown_face",
            "confidence": round(confidence, 4),
            "bbox":       bbox,
            "timestamp":  datetime.now().isoformat(),
        })

    def push_camera_offline(self, reason: str = ""):
        self.push({"event": "camera_offline", "message": reason})

    def push_frame_stats(self, fps: float, faces: int, processing_ms: int):
        self.push({
            "event":         "frame_stats",
            "fps":           round(fps, 1),
            "faces_detected": faces,
            "processing_ms": processing_ms,
        })

    def push_live_faces(self, faces: list):
        """Gửi tọa độ bboxes của tất cả khuôn mặt phát hiện được để vẽ Live khung."""
        self.push({
            "event": "live_faces",
            "faces": faces
        })


broadcaster = WSBroadcaster()
