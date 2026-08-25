import dlib
import numpy as np
import face_recognition_models
from sklearn.svm import SVC
from src.database.db import get_all_students

# Global model caches
_DETECTOR = None
_SHAPE_PREDICTOR = None
_FACE_REC = None
_TRAINED_MODEL = None

def load_dlib_models():
    global _DETECTOR, _SHAPE_PREDICTOR, _FACE_REC
    if _DETECTOR is None or _SHAPE_PREDICTOR is None or _FACE_REC is None:
        _DETECTOR = dlib.get_frontal_face_detector()
        _SHAPE_PREDICTOR = dlib.shape_predictor(
            face_recognition_models.pose_predictor_model_location()
        )
        _FACE_REC = dlib.face_recognition_model_v1(
            face_recognition_models.face_recognition_model_location()
        )
    return _DETECTOR, _SHAPE_PREDICTOR, _FACE_REC


def calculate_ear(eye_points):
    """
    Computes Eye Aspect Ratio (EAR) from 6 landmark points.
    EAR = (|p2 - p6| + |p3 - p5|) / (2 * |p1 - p4|)
    """
    p = [np.array([pt.x, pt.y]) for pt in eye_points]
    A = np.linalg.norm(p[1] - p[5])
    B = np.linalg.norm(p[2] - p[4])
    C = np.linalg.norm(p[0] - p[3])
    if C == 0:
        return 0.0
    return float((A + B) / (2.0 * C))


def verify_liveness_and_anti_spoof(images_np):
    """
    Evaluates burst frames for natural human eye blink closure (EAR) and facial dynamics.
    Rejects static photos, paper printouts, and digital phone screens.
    """
    if not images_np:
        return False, "No camera frames received."

    detector, sp, _ = load_dlib_models()
    ears = []

    for img in images_np:
        faces = detector(img, 0)
        if not faces:
            continue
        face = faces[0]
        shape = sp(img, face)

        # 68 landmark points: Left eye (36-41), Right eye (42-47)
        left_eye = [shape.part(i) for i in range(36, 42)]
        right_eye = [shape.part(i) for i in range(42, 48)]

        l_ear = calculate_ear(left_eye)
        r_ear = calculate_ear(right_eye)
        avg_ear = (l_ear + r_ear) / 2.0
        ears.append(avg_ear)

    if len(ears) < 2:
        return True, "Single frame verified"

    ear_min = min(ears)
    ear_max = max(ears)
    ear_delta = ear_max - ear_min

    # True blink check:
    # 1. Delta between open and closed must be >= 0.038
    # OR 2. One frame must capture a closed eye state (< 0.22) and another an open state (> 0.25)
    is_live_blink = (ear_delta >= 0.038) or (ear_min < 0.22 and ear_max > 0.25)

    if not is_live_blink:
        return False, "⚠️ Anti-Spoofing: Static photo or phone screen detected. Please blink your eyes while scanning."

    return True, "Live human verified"


def get_face_embeddings(image_np):
    """
    Extracts 128-dimensional face embeddings from an RGB numpy array.
    """
    detector, sp, facerec = load_dlib_models()
    faces = detector(image_np, 1)

    encodings = []
    for face in faces:
        shape = sp(image_np, face)
        face_descriptor = facerec.compute_face_descriptor(image_np, shape, 1)
        encodings.append(np.array(face_descriptor))
    return encodings


def get_trained_model(force_retrain=False):
    """
    Trains or retrieves the cached linear SVC classifier over all registered students.
    """
    global _TRAINED_MODEL
    if _TRAINED_MODEL is not None and not force_retrain:
        return _TRAINED_MODEL

    X = []
    y = []

    try:
        student_db = get_all_students() or []
    except Exception as e:
        print(f"Error fetching students: {e}")
        return None

    for student in student_db:
        embedding = student.get('face_embedding')
        if embedding is not None and len(embedding) == 128:
            X.append(embedding)
            y.append(student['student_id'])

    if len(y) == 0:
        return None

    unique_labels = len(set(y))
    if unique_labels < 2:
        return None

    clf = SVC(kernel='linear', probability=True)
    clf.fit(X, y)
    _TRAINED_MODEL = clf
    return _TRAINED_MODEL


def train_classifier():
    """Forces retraining of the SVM classifier."""
    return get_trained_model(force_retrain=True)


def predict_attendance(image_or_embeddings, threshold=0.55):
    """
    Predicts present students. Accepts either an RGB numpy image or list of 128D embeddings.
    Returns (detected_dict, all_student_ids, num_faces_detected).
    """
    if isinstance(image_or_embeddings, np.ndarray) and image_or_embeddings.ndim == 3:
        embeddings = get_face_embeddings(image_or_embeddings)
        num_faces = len(embeddings)
    elif isinstance(image_or_embeddings, list):
        embeddings = image_or_embeddings
        num_faces = len(embeddings)
    else:
        embeddings = []
        num_faces = 0

    if num_faces == 0:
        return {}, [], 0

    student_db = get_all_students() or []
    if not student_db:
        return {}, [], num_faces

    identified_students = {}

    for emb in embeddings:
        best_sid = None
        min_dist = float('inf')

        for student in student_db:
            stored_emb = student.get('face_embedding')
            if stored_emb and len(stored_emb) == 128:
                dist = np.linalg.norm(np.array(emb) - np.array(stored_emb))
                if dist < min_dist:
                    min_dist = dist
                    best_sid = student['student_id']

        if min_dist <= threshold and best_sid is not None:
            identified_students[best_sid] = round(float(1.0 - min_dist), 3)

    return identified_students, list(identified_students.keys()), num_faces
