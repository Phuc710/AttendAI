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
    is_deleted    INTEGER DEFAULT 0,      -- 1 = Đã xóa (soft delete), 0 = Hoạt động
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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

-- 3. GROUPS — Nhóm / Phòng ban / Đơn vị (Mặc định cho Nhân sự)
CREATE TABLE IF NOT EXISTS groups (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    group_code   TEXT UNIQUE NOT NULL,   -- VD: PHONGBAN01
    group_name   TEXT NOT NULL,          -- VD: Cyber Security
    description  TEXT,                   -- Mô tả / Ghi chú
    manager_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    location     TEXT,                   -- Địa điểm / Văn phòng
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_group_manager ON groups(manager_id);

-- 4. GROUP_MEMBERS — Danh sách thành viên nhóm (bảng trung gian)
CREATE TABLE IF NOT EXISTS group_members (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    added_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_gm_unique ON group_members(group_id, user_id);
CREATE INDEX IF NOT EXISTS idx_gm_group  ON group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_gm_user   ON group_members(user_id);

-- 5. SESSIONS — Buổi học / Ca điểm danh
CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_code        TEXT UNIQUE NOT NULL,  -- Auto: CNTT01-LTW-20260514-0730
    group_id            INTEGER NOT NULL REFERENCES groups(id),
    started_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at            DATETIME,              -- NULL = đang active
    late_threshold_mins INTEGER DEFAULT 15,   -- Phút cho phép trễ
    status              TEXT NOT NULL DEFAULT 'active'  -- active | closed
);
CREATE INDEX IF NOT EXISTS idx_sess_status   ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sess_group    ON sessions(group_id);

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

-- 8. SYSTEM_LOGS — Nhật ký sự kiện hệ thống
CREATE TABLE IF NOT EXISTS system_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    message     TEXT NOT NULL,
    detail      TEXT,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        # 1. Di trú dữ liệu cũ sang cấu trúc mới (groups / group_members) TRƯỚC KHI chạy SCHEMA
        try:
            table_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='classes'").fetchone()
            if table_check:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS groups (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_code   TEXT UNIQUE NOT NULL,
                        group_name   TEXT NOT NULL,
                        description  TEXT,
                        manager_id   INTEGER,
                        location     TEXT,
                        created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS group_members (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id   INTEGER NOT NULL,
                        user_id    INTEGER NOT NULL,
                        added_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO groups (id, group_code, group_name, description, created_at)
                    SELECT id, class_code, class_name, subject_code, created_at FROM classes
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO group_members (id, group_id, user_id, added_at)
                    SELECT id, class_id, user_id, added_at FROM class_students
                """)
                conn.execute("DROP TABLE IF EXISTS class_students")
                conn.execute("DROP TABLE IF EXISTS classes")
        except Exception as e:
            import sys
            print(f"Error migrating classes to groups phase 1: {e}", file=sys.stderr)

        # Di trú cột class_id thành group_id trong bảng sessions cũ trước khi chạy SCHEMA
        try:
            conn.execute("ALTER TABLE sessions RENAME COLUMN class_id TO group_id")
        except Exception:
            pass

        # 2. Khởi tạo toàn bộ schema chính thức
        conn.executescript(SCHEMA)

        # 3. Di trú các cột bổ sung
        try:
            conn.execute("ALTER TABLE users ADD COLUMN is_deleted INTEGER DEFAULT 0")
        except Exception:
            pass

        # Seed dữ liệu mặc định hệ thống nếu chưa có
        conn.execute("INSERT OR IGNORE INTO groups (id, group_code, group_name) VALUES (1, 'SYSTEM-DEFAULT-GROUP', 'Nhân sự')")
        conn.execute("INSERT OR IGNORE INTO sessions (id, session_code, group_id, status) VALUES (1, 'SYSTEM-DEFAULT-SESSION', 1, 'active')")

        # Backfill existing users and attendance logs if system_logs table does not contain them
        try:
            log_count = conn.execute("SELECT COUNT(*) FROM system_logs WHERE event_type IN ('checkin', 'register')").fetchone()[0]
            if log_count == 0:
                # Backfill users
                users = conn.execute("SELECT id, user_code, full_name, department, created_at FROM users").fetchall()
                for u in users:
                    try:
                        conn.execute(
                            "INSERT INTO system_logs (event_type, message, detail, created_at) VALUES (?, ?, ?, ?)",
                            ("register", f"Đăng ký nhân sự thành công: {u['full_name']} ({u['user_code']})", f"Phòng ban: {u['department'] or '—'}", u['created_at'])
                        )
                    except Exception as ue:
                        import sys
                        print(f"Skipping user log backfill: {ue}", file=sys.stderr)
                # Backfill checkins
                checkins = conn.execute("""
                    SELECT l.user_id, u.user_code, u.full_name, l.confidence, l.arrival_status, l.check_in_time 
                    FROM attendance_logs l
                    JOIN users u ON l.user_id = u.id
                """).fetchall()
                for c in checkins:
                    try:
                        conf = c['confidence']
                        conf_str = f"{conf:.2f}" if conf is not None else "1.00"
                        conn.execute(
                            "INSERT INTO system_logs (event_type, message, detail, created_at) VALUES (?, ?, ?, ?)",
                            ("checkin", f"Nhân viên {c['full_name']} ({c['user_code']}) check-in thành công", f"Độ tự tin: {conf_str}, Trạng thái: {c['arrival_status']}", c['check_in_time'])
                        )
                    except Exception as ce:
                        import sys
                        print(f"Skipping checkin log backfill: {ce}", file=sys.stderr)
            
            # Ghi nhận log khởi tạo hệ thống nếu bảng rỗng
            total_logs = conn.execute("SELECT COUNT(*) FROM system_logs").fetchone()[0]
            if total_logs == 0:
                conn.execute(
                    "INSERT INTO system_logs (event_type, message, detail) VALUES (?, ?, ?)",
                    ("system", "Hệ thống khởi động thành công", "Cơ sở dữ liệu đã được khởi tạo mới thành công.")
                )
        except Exception as e:
            import sys
            print(f"Error backfilling system logs: {e}", file=sys.stderr)


def log_event(event_type: str, message: str = "", detail: str = ""):
    """Ghi nhận nhật ký sự kiện hệ thống vào DB."""
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO system_logs (event_type, message, detail) VALUES (?, ?, ?)",
                (event_type, message, detail)
            )
    except Exception as e:
        import sys
        print(f"Error logging event to database: {e}", file=sys.stderr)
