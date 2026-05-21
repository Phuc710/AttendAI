"""main.py — FastAPI app entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from database import init_db, log_event
from services.face_service import load_model
from services import match_service
from services.attendance_service import get_active_session
from services.ws_service import broadcaster
from api import router as api_router
from config import HOST, PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ─── Lifespan (startup / shutdown) ────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log.info("=== Face Attendance System Starting ===")
    init_db()
    log.info("DB initialized")

    load_model()

    match_service.reload_index()

    # Nếu server khởi động lại khi session đang active → load lại class index
    active = get_active_session()
    if active:
        match_service.load_class_index(active["class_id"])
        log.info(f"Auto-loaded class index: class_id={active['class_id']}")

    log.info("=== System READY ===")
    yield

    # Shutdown
    from services.camera_service import stop
    stop()
    log.info("=== System Stopped ===")


# ─── App ──────────────────────────────────────────────────

app = FastAPI(
    title="Face Attendance API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST & camera API
app.include_router(api_router)

# WebSocket realtime
@app.websocket("/ws/attendance")
async def ws_attendance(websocket: WebSocket):
    await broadcaster.connect(websocket)

# Serve storage files (snapshots, enrolled photos)
from config import STORAGE_DIR
if STORAGE_DIR.exists():
    app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage")

# Serve frontend static files
if (FRONTEND_DIR / "kiosk").exists():
    app.mount("/kiosk",  StaticFiles(directory=FRONTEND_DIR / "kiosk",  html=True), name="kiosk")
if (FRONTEND_DIR / "admin").exists():
    app.mount("/admin",  StaticFiles(directory=FRONTEND_DIR / "admin",  html=True), name="admin")

@app.get("/")
def root():
    """Redirect root → kiosk UI."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/kiosk")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
