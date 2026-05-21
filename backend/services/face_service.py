"""face_service.py — InsightFace: load model, detect, embed."""

import logging
import numpy as np
import cv2
import insightface
from insightface.app import FaceAnalysis
from config import MODEL_NAME, MIN_FACE_SIZE, MIN_DET_SCORE

log = logging.getLogger("face_service")

_app: FaceAnalysis | None = None


def load_model():
    global _app
    log.info(f"Loading InsightFace model: {MODEL_NAME} ...")
    _app = FaceAnalysis(name=MODEL_NAME, providers=["CPUExecutionProvider"])
    _app.prepare(ctx_id=0, det_size=(640, 640))
    log.info("InsightFace model loaded.")


def get_model() -> FaceAnalysis:
    if _app is None:
        raise RuntimeError("Model chưa được load. Gọi load_model() trước.")
    return _app


# ─── Detect + Embed ───────────────────────────────────────

def detect_and_embed(frame: np.ndarray) -> list[dict]:
    """
    Detect toàn bộ khuôn mặt trong frame.
    Trả về list [{ bbox, embedding, det_score, quality_ok }].
    """
    app = get_model()
    faces = app.get(frame)
    results = []
    for face in faces:
        x1, y1, x2, y2 = face.bbox.astype(int)
        w, h = x2 - x1, y2 - y1

        if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE:
            continue
        if face.det_score < MIN_DET_SCORE:
            continue

        emb = face.embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm == 0:
            continue
        emb /= norm  # normalize về unit vector

        results.append({
            "bbox":      {"x": int(x1), "y": int(y1), "w": int(w), "h": int(h)},
            "embedding": emb,
            "det_score": float(face.det_score),
        })
    return results


def embed_image(img: np.ndarray) -> tuple[np.ndarray | None, float, int]:
    """
    Dùng cho enrollment: extract embedding từ 1 ảnh.
    Trả về (embedding, det_score, face_count).
    - face_count = 0: không detect được mặt
    - face_count = 1: OK (kể cả khi nhiều mặt, lấy mặt score cao nhất)
    """
    app = get_model()
    faces = app.get(img)
    if not faces:
        return None, 0.0, 0
    # Lấy mặt có det_score cao nhất (tốt nhất trong ảnh)
    face = max(faces, key=lambda f: f.det_score)
    emb = face.embedding.astype(np.float32)
    emb /= np.linalg.norm(emb)
    return emb, float(face.det_score), 1


def crop_face(frame: np.ndarray, bbox: dict) -> np.ndarray:
    x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
    h_f, w_f = frame.shape[:2]
    return frame[max(0, y):min(h_f, y+h), max(0, x):min(w_f, x+w)]
