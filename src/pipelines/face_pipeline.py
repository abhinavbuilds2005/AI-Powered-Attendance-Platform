

import dlib
import numpy as np
import face_recognition_models
from sklearn.svm import SVC

from src.database.db import get_all_students

_DLIB_MODELS = None
_TRAINED_MODEL = None

def load_dlib_models():
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

def get_face_embeddings(image_np):
    detector, sp, facerec = load_dlib_models()
    faces = detector(image_np, 1)

    encodings= []

    for face in faces:
        shape = sp(image_np, face)
        face_descriptor = facerec.compute_face_descriptor(image_np, shape, 1) #128 embedding

        encodings.append(np.array(face_descriptor))
    return encodings

def get_trained_model():
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
        if embedding:
            X.append(np.array(embedding))
            y.append(student.get('student_id'))

    if len(X) == 0:
        return 0
    
    clf = SVC(kernel='linear', probability=True, class_weight='balanced')

    try:
        clf.fit(X, y)
    except ValueError:
        pass

    _TRAINED_MODEL = {'clf': clf, 'X':X, "y":y}
    return _TRAINED_MODEL


def train_classifier():
    global _TRAINED_MODEL
    _TRAINED_MODEL = None
    model_data = get_trained_model()
    return bool(model_data)

def predict_attendance(class_image_np):
    encodings = get_face_embeddings(class_image_np)

    detected_student = {}

    model_data = get_trained_model()

    if not model_data:
        return detected_student, [], len(encodings)
    
    clf = model_data['clf']
    X_train = model_data['X']
    y_train = model_data['y']

    all_students = sorted(list(set(y_train)))

    for encoding in encodings:
        if len(all_students)>= 2:
            predicted_id= int(clf.predict([encoding])[0])
        else:
            predicted_id = int(all_students[0])

        student_embedding = X_train[y_train.index(predicted_id)]

        best_match_score = np.linalg.norm(student_embedding - encoding)

        resemblance_threshold = 0.6

        if best_match_score <= resemblance_threshold:
            detected_student[predicted_id] = True
    return detected_student, all_students, len(encodings)


