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
    h_orig, w_orig = frame.shape[:2]
    max_w = 640
    if w_orig > max_w:
        scale = max_w / w_orig
        new_w = max_w
        new_h = int(h_orig * scale)
        resized_frame = cv2.resize(frame, (new_w, new_h))
    else:
        scale = 1.0
        resized_frame = frame

    app = get_model()
    faces = app.get(resized_frame)
    results = []
    
    for face in faces:
        x1, y1, x2, y2 = face.bbox.astype(int)
        orig_x1 = int(x1 / scale)
        orig_y1 = int(y1 / scale)
        orig_x2 = int(x2 / scale)
        orig_y2 = int(y2 / scale)
        orig_w = orig_x2 - orig_x1
        orig_h = orig_y2 - orig_y1

        if orig_w < MIN_FACE_SIZE or orig_h < MIN_FACE_SIZE:
            continue
        if face.det_score < MIN_DET_SCORE:
            continue

        emb = face.embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm == 0:
            continue
        emb /= norm  # normalize về unit vector

        results.append({
            "bbox":      {"x": orig_x1, "y": orig_y1, "w": orig_w, "h": orig_h},
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
