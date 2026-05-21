"""api/camera.py — Camera control + MJPEG stream."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response
import services.camera_service as cam_svc
from services.match_service import index_size, index_info
from services.attendance_service import get_active_session

router = APIRouter(prefix="/api/camera", tags=["camera"])


@router.get("/stream")
def stream():
    """MJPEG stream — nhúng bằng <img src='/api/camera/stream'>."""
    if not cam_svc.status()["connected"]:
        raise HTTPException(status_code=404, detail="Camera offline")

    return StreamingResponse(
        cam_svc.mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/status")
def get_status():
    return cam_svc.status()


@router.post("/start")
def start_camera(source: str | None = None):
    ok, msg = cam_svc.start(source)
    return {"ok": ok, "message": msg}


@router.post("/stop")
def stop_camera():
    cam_svc.stop()
    return {"ok": True}


@router.post("/restart")
def restart_camera():
    cam_svc.stop()
    import time; time.sleep(0.5)
    ok, msg = cam_svc.start()
    return {"ok": ok, "message": msg}


@router.get("/system/health")
def health():
    s  = cam_svc.status()
    ix = index_info()
    return {
        "status":            "ok",
        "db":                "connected",
        "model":             "loaded",
        "camera":            "online" if s["connected"] else "offline",
        "fps":               s["fps"],
        "embeddings_loaded": ix["global_vectors"],
        "faiss_available":   ix["faiss_available"],
        "index_type":        ix["global_index_type"],
        "class_id_loaded":   ix["class_id_loaded"],
        "class_vectors":     ix["class_vectors"],
        "active_session":    get_active_session() is not None,
    }
