import dlib
import numpy as np
import face_recognition_models
from sklearn.svm import SVC
from typing import Dict, List, Tuple, Any

from src.services.db_service import get_all_students

_DLIB_MODELS = None
_TRAINED_MODEL = None

def load_dlib_models():
    """Lazy load dlib models to keep startup times fast."""
    global _DLIB_MODELS
    if _DLIB_MODELS is None:
        detector = dlib.get_frontal_face_detector()
        sp = dlib.shape_predictor(
            face_recognition_models.pose_predictor_model_location()
        )
        facerec = dlib.face_recognition_model_v1(
            face_recognition_models.face_recognition_model_location()
        )
        _DLIB_MODELS = (detector, sp, facerec)
    return _DLIB_MODELS

def get_face_embeddings(image_np: np.ndarray) -> List[np.ndarray]:
    """Extract face embeddings (128-D) from a numpy image array."""
    detector, sp, facerec = load_dlib_models()
    faces = detector(image_np, 1)

    encodings = []
    for face in faces:
        shape = sp(image_np, face)
        face_descriptor = facerec.compute_face_descriptor(image_np, shape, 1)
        encodings.append(np.array(face_descriptor))
    return encodings

def get_trained_model() -> Any:
    """Load or train face classifier SVM model on student embeddings."""
    global _TRAINED_MODEL
    if _TRAINED_MODEL is not None:
        return _TRAINED_MODEL

    X = []
    y = []

    student_db = get_all_students()
    if not student_db:
        return None

    for student in student_db:
        embedding = student.get('face_embedding')
        student_id = student.get('student_id')
        if embedding and student_id is not None:
            try:
                vector = np.asarray(embedding, dtype=np.float64)
                if vector.shape == (128,) and np.isfinite(vector).all():
                    X.append(vector)
                    y.append(int(student_id))
            except (TypeError, ValueError):
                continue

    if len(X) == 0:
        return None

    if len(set(y)) < 2:
        _TRAINED_MODEL = {'clf': None, 'X': X, 'y': y}
        return _TRAINED_MODEL

    clf = SVC(kernel='linear', probability=True, class_weight='balanced')
    try:
        clf.fit(X, y)
    except ValueError:
        return None

    _TRAINED_MODEL = {'clf': clf, 'X': X, 'y': y}
    return _TRAINED_MODEL

def train_classifier() -> bool:
    """Force retrain face classifier model."""
    global _TRAINED_MODEL
    _TRAINED_MODEL = None
    model_data = get_trained_model()
    return bool(model_data)

def predict_attendance(
    class_image_np: np.ndarray
) -> Tuple[Dict[int, bool], List[int], int]:
    """Recognize students' faces in class photo.

    Returns:
        Dict: mapping student_id to True (if detected)
        List: all enrolled student ids
        int: number of faces detected in the photo
    """
    encodings = get_face_embeddings(class_image_np)
    detected_students = {}

    model_data = get_trained_model()
    if not model_data:
        return detected_students, [], len(encodings)

    X_train = model_data['X']
    y_train = model_data['y']
    all_students = sorted(list(set(y_train)))

    if len(X_train) == 0:
        return detected_students, [], len(encodings)

    for encoding in encodings:
        best_sid = None
        min_dist = float('inf')

        for stored_emb, sid in zip(X_train, y_train):
            try:
                dist = float(np.linalg.norm(np.asarray(stored_emb) - np.asarray(encoding)))
                if dist < min_dist:
                    min_dist = dist
                    best_sid = sid
            except Exception:
                continue

        # Standard face recognition Euclidean distance threshold (dlib/FaceNet 0.60)
        if best_sid is not None and min_dist <= 0.60:
            detected_students[int(best_sid)] = True

    return detected_students, all_students, len(encodings)
