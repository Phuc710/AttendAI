"""config.py — Load .env, định nghĩa toàn bộ constants."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR    = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "storage"

# Admin
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Camera
CAMERA_SOURCE  = os.getenv("CAMERA_SOURCE", "0")
CAMERA_WIDTH   = int(os.getenv("CAMERA_WIDTH",  "1280"))
CAMERA_HEIGHT  = int(os.getenv("CAMERA_HEIGHT", "720"))
CAMERA_FPS     = int(os.getenv("CAMERA_FPS",    "30"))
FRAME_SKIP     = int(os.getenv("FRAME_SKIP",    "3"))

# AI
MODEL_NAME          = os.getenv("MODEL_NAME", "buffalo_l")
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.45"))
MIN_FACE_SIZE       = int(os.getenv("MIN_FACE_SIZE",  "60"))
MIN_DET_SCORE       = float(os.getenv("MIN_DET_SCORE", "0.5"))

# DB
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "face_attendance.db")

# Storage
ENROLLED_DIR  = STORAGE_DIR / "enrolled"
SNAPSHOTS_DIR = STORAGE_DIR / "snapshots"
UNKNOWN_DIR   = STORAGE_DIR / "unknown"

SAVE_UNKNOWN   = os.getenv("SAVE_UNKNOWN_FACE",         "true").lower() == "true"
SAVE_SNAPSHOT  = os.getenv("SAVE_ATTENDANCE_SNAPSHOT",  "true").lower() == "true"

# Duplicate guard
DUPLICATE_TIME_WINDOW = int(os.getenv("DUPLICATE_TIME_WINDOW", "30"))

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Tạo thư mục storage nếu chưa có
for d in (ENROLLED_DIR, SNAPSHOTS_DIR, UNKNOWN_DIR):
    d.mkdir(parents=True, exist_ok=True)
