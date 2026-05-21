"""database.py — SQLite production schema đầy đủ cho hệ thống điểm danh."""

import sqlite3
from contextlib import contextmanager
from config import DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode  = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
-- 1. USERS — Tài khoản dùng chung (Nhân sự)
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_code     TEXT UNIQUE NOT NULL,   -- Mã nhân viên (Staff ID)
    full_name     TEXT NOT NULL,
    department    TEXT,                   -- Phòng ban
    role          TEXT NOT NULL DEFAULT 'student',  -- student | teacher | admin
    email         TEXT,
    phone         TEXT,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- 2. FACE EMBEDDINGS — Vector khuôn mặt AI
CREATE TABLE IF NOT EXISTS face_embeddings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    embedding_json TEXT NOT NULL,    -- JSON array 512 floats (ArcFace)
    image_path     TEXT,
    quality_score  REAL,             -- det_score 0.0–1.0
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_emb_user ON face_embeddings(user_id);

-- 3. CLASSES — Lớp học / Môn học (Mặc định cho Nhân sự)
CREATE TABLE IF NOT EXISTS classes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    class_code   TEXT UNIQUE NOT NULL,   -- VD: CNTT01-LTW-2026
    class_name   TEXT NOT NULL,          -- VD: Lập Trình Web
    subject_code TEXT,                   -- VD: IT001
    teacher_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    room         TEXT,
    academic_year TEXT,                  -- VD: 2025-2026
    semester     TEXT,                   -- VD: HK1
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_class_teacher ON classes(teacher_id);

-- 4. CLASS_STUDENTS — Danh sách lớp (bảng trung gian)
CREATE TABLE IF NOT EXISTS class_students (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id   INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    added_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cs_unique ON class_students(class_id, user_id);
CREATE INDEX IF NOT EXISTS idx_cs_class  ON class_students(class_id);
CREATE INDEX IF NOT EXISTS idx_cs_user   ON class_students(user_id);

-- 5. SESSIONS — Buổi học / Phiên điểm danh
CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_code        TEXT UNIQUE NOT NULL,  -- Auto: CNTT01-LTW-20260514-0730
    class_id            INTEGER NOT NULL REFERENCES classes(id),
    started_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at            DATETIME,              -- NULL = đang active
    late_threshold_mins INTEGER DEFAULT 15,   -- Phút cho phép trễ
    status              TEXT NOT NULL DEFAULT 'active'  -- active | closed
);
CREATE INDEX IF NOT EXISTS idx_sess_status   ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sess_class    ON sessions(class_id);

-- 6. ATTENDANCE_LOGS — Log điểm danh
CREATE TABLE IF NOT EXISTS attendance_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    check_in_time   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    check_out_time  DATETIME,                -- NULL = chưa check-out
    confidence      REAL NOT NULL,           -- Cosine similarity 0.0–1.0
    check_in_method TEXT NOT NULL DEFAULT 'face',  -- face | manual
    arrival_status  TEXT NOT NULL DEFAULT 'on_time',  -- on_time | late
    snapshot_path   TEXT,                    -- Ảnh chụp lúc điểm danh
    status          TEXT NOT NULL DEFAULT 'checked_in'
);
CREATE INDEX IF NOT EXISTS idx_log_session ON attendance_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_log_user    ON attendance_logs(user_id);

-- Chống trùng tuyệt đối: 1 SV chỉ 1 lần checked_in / session
CREATE UNIQUE INDEX IF NOT EXISTS idx_log_no_dup
    ON attendance_logs(session_id, user_id)
    WHERE status = 'checked_in';

-- 7. SYSTEM_CONFIGS — Cấu hình hệ thống (key-value)
CREATE TABLE IF NOT EXISTS system_configs (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    description TEXT,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Giá trị mặc định
INSERT OR IGNORE INTO system_configs (key, value, description) VALUES
    ('match_threshold',      '0.45', 'Ngưỡng similarity để nhận diện thành công'),
    ('late_threshold_mins',  '15',   'Phút tối đa tính là đúng giờ'),
    ('kiosk_auto_close',     '0',    'Tự đóng session sau N phút (0 = tắt)'),
    ('save_snapshot',        '1',    'Lưu ảnh khi điểm danh (1=có, 0=không)'),
    ('duplicate_window_sec', '30',   'Thời gian (giây) cache chống duplicate in-memory');
"""


def init_db():
    """Khởi tạo toàn bộ schema và hạt giống dữ liệu hệ thống."""
    with get_db() as conn:
        conn.executescript(SCHEMA)
        # Nâng cấp database nếu là DB cũ chưa có cột department
        try:
            conn.execute("ALTER TABLE users ADD COLUMN department TEXT")
        except sqlite3.OperationalError:
            pass  # Cột đã tồn tại
            
        # Seed dữ liệu mặc định hệ thống nếu chưa có
        conn.execute("INSERT OR IGNORE INTO classes (id, class_code, class_name) VALUES (1, 'SYSTEM-DEFAULT-CLASS', 'Nhân sự')")
        conn.execute("INSERT OR IGNORE INTO sessions (id, session_code, class_id, status) VALUES (1, 'SYSTEM-DEFAULT-SESSION', 1, 'active')")


def log_event(event_type: str, message: str = "", detail: str = ""):
    """Hàm giữ tương thích — không lưu gì vào DB."""
    pass
