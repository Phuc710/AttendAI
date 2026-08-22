"""match_service.py — FAISS-powered face matching với per-class index.

Kiến trúc:
─────────────────────────────────────────────────────────────────────
  GLOBAL INDEX  (faiss.IndexFlatIP)
    • Chứa TẤT CẢ vector đã normalize → cosine = inner-product.
    • Dùng khi không có active session (fallback toàn trường).
    • Với < 10.000 người: IndexFlatIP đã đủ nhanh (~1-3 ms).
    • Với > 10.000 người: tự động nâng lên IndexIVFFlat (clustering).

  SESSION / CLASS INDEX  (faiss.IndexFlatIP)
    • Khi Kiosk start session → load CHỈ vector của lớp đó vào RAM.
    • Thường 30-50 SV → match < 1 ms, không cần IVF.
    • Đây là index ưu tiên khi có active session.

Thứ tự ưu tiên match():
    1. class_index (nếu có active session + lớp đã load)
    2. global_index (fallback)
─────────────────────────────────────────────────────────────────────
"""

import json
import logging
import time
import threading
import numpy as np

try:
    # pyrefly: ignore [missing-import]
    import faiss
    FAISS_OK = True
except ImportError:
    FAISS_OK = False

from database import get_db
from config import FACE_MATCH_THRESHOLD

log = logging.getLogger("match_service")

# ─── Constants ────────────────────────────────────────────
DIM = 512           # ArcFace buffalo_l embedding dimension
IVF_THRESHOLD = 1000  # Số vector tối thiểu để dùng IVF thay FlatIP

# ─── State ────────────────────────────────────────────────
_lock = threading.RLock()

# Global index (toàn trường)
_global_index  = None      # faiss.Index hoặc None
_global_meta: list[dict] = []  # [{user_id, user_code, full_name}]

# Group index (per session)
_group_index   = None
_group_meta: list[dict] = []
_group_id: int | None = None   # group_id đang được load

# Fallback numpy (nếu faiss không cài được)
_np_embeddings: np.ndarray | None = None  # (N, 512)
_np_meta: list[dict] = []


# ─── Helpers ──────────────────────────────────────────────

def _normalize(emb: np.ndarray) -> np.ndarray:
    """Normalize về unit vector (cosine = inner product sau bước này)."""
    norm = np.linalg.norm(emb)
    return emb / norm if norm > 0 else emb


def _build_faiss_index(embeddings: np.ndarray) -> "faiss.Index":
    """
    Xây index tối ưu tuỳ theo số lượng vector:
    - < IVF_THRESHOLD  → IndexFlatIP (exact, nhanh với dataset nhỏ)
    - >= IVF_THRESHOLD → IndexIVFFlat với nlist = sqrt(N) (approximate, nhanh với dataset lớn)
    """
    n = len(embeddings)
    if n == 0:
        idx = faiss.IndexFlatIP(DIM)
        return idx

    if n < IVF_THRESHOLD:
        idx = faiss.IndexFlatIP(DIM)
        idx.add(embeddings)
        log.debug(f"Built IndexFlatIP: {n} vectors")
    else:
        nlist  = max(4, int(n ** 0.5))   # nlist ~ sqrt(N)
        nlist  = min(nlist, n // 4)       # không vượt N/4
        quantizer = faiss.IndexFlatIP(DIM)
        idx = faiss.IndexIVFFlat(quantizer, DIM, nlist, faiss.METRIC_INNER_PRODUCT)
        # Train cần ít nhất nlist * 39 vectors
        train_data = embeddings if n >= nlist * 39 else np.tile(embeddings, (40, 1))[:nlist*39]
        idx.train(train_data)
        idx.add(embeddings)
        idx.nprobe = max(1, nlist // 4)   # Kiểm tra 25% các cụm (trade-off tốc/độ chính xác)
        log.debug(f"Built IndexIVFFlat: {n} vectors, nlist={nlist}, nprobe={idx.nprobe}")

    return idx


def _load_embeddings_from_db(user_ids: list[int] | None = None) -> tuple[np.ndarray, list[dict]]:
    """
    Load embedding từ DB.
    user_ids=None → toàn trường.
    user_ids=[...] → chỉ những user trong danh sách.
    """
    with get_db() as conn:
        if user_ids is None:
            rows = conn.execute("""
                SELECT fe.user_id, fe.embedding_json, fe.image_path,
                       u.user_code, u.full_name, u.department
                FROM face_embeddings fe
                JOIN users u ON u.id = fe.user_id
                ORDER BY fe.user_id, fe.created_at DESC
            """).fetchall()
        else:
            placeholders = ",".join("?" * len(user_ids))
            rows = conn.execute(f"""
                SELECT fe.user_id, fe.embedding_json, fe.image_path,
                       u.user_code, u.full_name, u.department
                FROM face_embeddings fe
                JOIN users u ON u.id = fe.user_id
                WHERE fe.user_id IN ({placeholders})
                ORDER BY fe.user_id, fe.created_at DESC
            """, user_ids).fetchall()

    embeddings, meta = [], []
    seen_users: set[int] = set()

    for row in rows:
        uid = row["user_id"]
        # Chỉ lấy embedding mới nhất của mỗi user (đã ORDER BY created_at DESC)
        if uid in seen_users:
            continue
        seen_users.add(uid)

        emb = np.array(json.loads(row["embedding_json"]), dtype=np.float32)
        emb = _normalize(emb)
        embeddings.append(emb)
        meta.append({
            "user_id":   uid,
            "user_code": row["user_code"],
            "full_name": row["full_name"],
            "face_image": row["image_path"],
            "department": row["department"],
        })

    if embeddings:
        return np.stack(embeddings).astype(np.float32), meta
    return np.empty((0, DIM), dtype=np.float32), []


# ─── Public: Reload global index ──────────────────────────

def reload_index():
    """
    Load TẤT CẢ embedding vào global FAISS index.
    Gọi sau enrollment hoặc khi start server.
    """
    global _global_index, _global_meta, _np_embeddings, _np_meta
    t0 = time.perf_counter()

    embeddings, meta = _load_embeddings_from_db()

    with _lock:
        _global_meta = meta
        if FAISS_OK and len(embeddings) > 0:
            _global_index = _build_faiss_index(embeddings)
            _np_embeddings = None
            _np_meta       = []
        else:
            # Fallback: numpy dot product (không cần faiss)
            _global_index  = None
            _np_embeddings = embeddings if len(embeddings) > 0 else None
            _np_meta       = meta

    ms = (time.perf_counter() - t0) * 1000
    log.info(f"Global index reloaded: {len(meta)} users | FAISS={FAISS_OK} | {ms:.1f}ms")

    # Nếu đang có group_id được load (phiên hoạt động), reload luôn group index
    if _group_id is not None:
        load_group_index(_group_id)


# ─── Public: Load group index ─────────────────────────────

def load_group_index(group_id: int):
    """
    Khi Kiosk bắt đầu session → gọi hàm này để load ĐÚNG danh sách nhóm đó vào RAM.
    Chỉ match những người trong nhóm → nhanh hơn, chính xác hơn.
    """
    global _group_index, _group_meta, _group_id
    t0 = time.perf_counter()

    # Lấy user_id trong nhóm
    with get_db() as conn:
        user_ids = [r[0] for r in conn.execute(
            "SELECT user_id FROM group_members WHERE group_id=?", (group_id,)
        ).fetchall()]

    if not user_ids:
        log.warning(f"Group {group_id} has no members enrolled.")
        with _lock:
            _group_index = None
            _group_meta  = []
            _group_id    = group_id
        return

    embeddings, meta = _load_embeddings_from_db(user_ids)

    with _lock:
        _group_meta  = meta
        _group_id    = group_id
        if FAISS_OK and len(embeddings) > 0:
            # Nhóm < 1000 người → FlatIP (exact, ~0.1 ms)
            _group_index = faiss.IndexFlatIP(DIM)
            _group_index.add(embeddings)
        else:
            _group_index = None

    ms = (time.perf_counter() - t0) * 1000
    log.info(f"Group index loaded: group_id={group_id} | {len(meta)} users | {ms:.1f}ms")


def clear_group_index():
    """Xóa group index khi session kết thúc."""
    global _group_index, _group_meta, _group_id
    with _lock:
        _group_index = None
        _group_meta  = []
        _group_id    = None
    log.info("Group index cleared.")


# ─── Search helpers ───────────────────────────────────────

def _search_faiss(index: "faiss.Index", meta: list[dict], query: np.ndarray) -> tuple[dict | None, float]:
    """Inner search trên 1 faiss index."""
    if index is None or not meta:
        return None, 0.0
    q = query.reshape(1, DIM).astype(np.float32)
    scores, ids = index.search(q, 1)
    best_score = float(scores[0][0])
    best_id    = int(ids[0][0])
    if best_id < 0 or best_score < FACE_MATCH_THRESHOLD:
        return None, best_score
    return meta[best_id], best_score


def _search_numpy(query: np.ndarray) -> tuple[dict | None, float]:
    """Numpy fallback nếu faiss chưa cài."""
    if _np_embeddings is None or len(_np_meta) == 0:
        return None, 0.0
    scores    = _np_embeddings @ query
    best_idx  = int(np.argmax(scores))
    best_score = float(scores[best_idx])
    if best_score < FACE_MATCH_THRESHOLD:
        return None, best_score
    return _np_meta[best_idx], best_score


# ─── Public: match ────────────────────────────────────────

def match(query_emb: np.ndarray) -> tuple[dict | None, float]:
    """
    Tìm user khớp với query_emb.

    Thứ tự ưu tiên:
      1. Class index (nếu đã load → chỉ match SV trong lớp đó)
      2. Global FAISS index (toàn trường)
      3. Numpy fallback (nếu faiss chưa cài)

    Trả về: (user_info_dict | None, score)
    """
    t0 = time.perf_counter()
    query = _normalize(query_emb.astype(np.float32))

    with _lock:
        # ── Ưu tiên 1: Group index ──
        if _group_index is not None and _group_meta:
            user, score = _search_faiss(_group_index, _group_meta, query)
            ms = (time.perf_counter() - t0) * 1000
            log.debug(f"[GROUP-FAISS] match={user and user['user_code']} score={score:.3f} {ms:.1f}ms")
            return user, score

        # ── Ưu tiên 2: Global FAISS ──
        if FAISS_OK and _global_index is not None and _global_meta:
            user, score = _search_faiss(_global_index, _global_meta, query)
            ms = (time.perf_counter() - t0) * 1000
            log.debug(f"[GLOBAL-FAISS] match={user and user['user_code']} score={score:.3f} {ms:.1f}ms")
            return user, score

        # ── Ưu tiên 3: Numpy fallback ──
        user, score = _search_numpy(query)
        ms = (time.perf_counter() - t0) * 1000
        log.debug(f"[NUMPY] match={user and user['user_code']} score={score:.3f} {ms:.1f}ms")
        return user, score


# ─── Stats ────────────────────────────────────────────────

def index_info() -> dict:
    with _lock:
        return {
            "faiss_available":    FAISS_OK,
            "global_vectors":     len(_global_meta),
            "global_index_type":  type(_global_index).__name__ if _global_index else "numpy_fallback",
            "group_id_loaded":    _group_id,
            "group_vectors":      len(_group_meta),
        }

def index_size() -> int:
    return len(_global_meta)
