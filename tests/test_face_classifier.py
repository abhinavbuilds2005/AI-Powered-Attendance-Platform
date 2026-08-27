import numpy as np
import pytest
from unittest.mock import patch, MagicMock
import threading
import time

from src.services.face_service import (
    get_trained_model,
    invalidate_classifier_cache,
    train_classifier,
    predict_attendance
)
import src.services.face_service as face_service_module


@pytest.fixture(autouse=True)
def reset_classifier_cache():
    """Ensure clean classifier cache before and after every test."""
    invalidate_classifier_cache()
    yield
    invalidate_classifier_cache()


def test_cache_invalidation():
    """Test that invalidate_classifier_cache clears the in-memory trained model."""
    face_service_module._TRAINED_MODEL = {'clf': None, 'X': [np.zeros(128)], 'y': [1]}
    assert face_service_module._TRAINED_MODEL is not None

    invalidate_classifier_cache()
    assert face_service_module._TRAINED_MODEL is None


def test_lazy_classifier_rebuild_empty_db():
    """Test get_trained_model returns None when student database is empty."""
    with patch('src.services.face_service.get_all_students', return_value=[]):
        model = get_trained_model()
        assert model is None
        assert face_service_module._TRAINED_MODEL is None


def test_lazy_classifier_rebuild_single_student():
    """Test lazy rebuild with a single student uses Euclidean fallback without failing SVM."""
    fake_student = [
        {'student_id': 101, 'name': 'Alice', 'face_embedding': [0.1] * 128}
    ]
    with patch('src.services.face_service.get_all_students', return_value=fake_student) as mock_get:
        model = get_trained_model()
        assert mock_get.call_count == 1
        assert model is not None
        assert model['clf'] is None
        assert len(model['X']) == 1
        assert model['y'] == [101]

        # Second call should use cache without calling DB again
        model_cached = get_trained_model()
        assert mock_get.call_count == 1
        assert model_cached is model


def test_lazy_classifier_rebuild_multiple_students():
    """Test lazy rebuild with multiple students builds SVM classifier."""
    fake_students = [
        {'student_id': 101, 'name': 'Alice', 'face_embedding': np.random.randn(128).tolist()},
        {'student_id': 102, 'name': 'Bob', 'face_embedding': np.random.randn(128).tolist()}
    ]
    with patch('src.services.face_service.get_all_students', return_value=fake_students) as mock_get:
        model = get_trained_model()
        assert mock_get.call_count == 1
        assert model is not None
        assert len(model['X']) == 2
        assert set(model['y']) == {101, 102}


def test_malformed_embeddings_filtered_out():
    """Test that non-128D, NaN, None, or invalid embeddings are filtered out safely."""
    fake_students = [
        {'student_id': 1, 'name': 'Valid', 'face_embedding': [0.5] * 128},
        {'student_id': 2, 'name': 'WrongDim', 'face_embedding': [0.5] * 64},
        {'student_id': 3, 'name': 'WithNaN', 'face_embedding': [float('nan')] * 128},
        {'student_id': 4, 'name': 'NoEmbedding', 'face_embedding': None},
        {'student_id': 5, 'name': 'StringEmbedding', 'face_embedding': "not-an-array"},
        {'student_id': None, 'name': 'NoID', 'face_embedding': [0.2] * 128},
    ]
    with patch('src.services.face_service.get_all_students', return_value=fake_students):
        model = get_trained_model()
        assert model is not None
        assert len(model['X']) == 1
        assert model['y'] == [1]


def test_predict_attendance_single_student():
    """Test recognition matching for single registered student."""
    emb_alice = np.array([0.1] * 128, dtype=np.float64)
    fake_student = [{'student_id': 101, 'name': 'Alice', 'face_embedding': emb_alice.tolist()}]

    with patch('src.services.face_service.get_all_students', return_value=fake_student):
        with patch('src.services.face_service.get_face_embeddings', return_value=[emb_alice]):
            dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
            detected, all_ids, num_faces = predict_attendance(dummy_img)

            assert 101 in detected
            assert detected[101] is True
            assert all_ids == [101]
            assert num_faces == 1


def test_existing_students_remain_recognizable_after_new_student_registration():
    """Test that existing students stay recognizable when a new student is added and cache invalidated."""
    emb_alice = np.array([0.05] * 128, dtype=np.float64)
    emb_bob = np.array([0.95] * 128, dtype=np.float64)

    # Initial state: only Alice
    db_students = [{'student_id': 101, 'name': 'Alice', 'face_embedding': emb_alice.tolist()}]
    with patch('src.services.face_service.get_all_students', side_effect=lambda: list(db_students)):
        # 1. Alice recognized
        with patch('src.services.face_service.get_face_embeddings', return_value=[emb_alice]):
            detected, _, _ = predict_attendance(np.zeros((10, 10, 3), dtype=np.uint8))
            assert 101 in detected

        # 2. Bob registers -> DB updated and cache invalidated
        db_students.append({'student_id': 102, 'name': 'Bob', 'face_embedding': emb_bob.tolist()})
        invalidate_classifier_cache()

        # 3. Predict Alice -> Still recognized, cache lazily rebuilt with both
        with patch('src.services.face_service.get_face_embeddings', return_value=[emb_alice]):
            detected, all_ids, _ = predict_attendance(np.zeros((10, 10, 3), dtype=np.uint8))
            assert 101 in detected
            assert 102 not in detected
            assert set(all_ids) == {101, 102}

        # 4. Predict Bob -> Also recognized
        with patch('src.services.face_service.get_face_embeddings', return_value=[emb_bob]):
            detected, all_ids, _ = predict_attendance(np.zeros((10, 10, 3), dtype=np.uint8))
            assert 102 in detected
            assert 101 not in detected


def test_thread_safe_lazy_loading():
    """Test that concurrent requests safely load classifier without race conditions."""
    fake_students = [
        {'student_id': 101, 'name': 'Alice', 'face_embedding': [0.1] * 128},
        {'student_id': 102, 'name': 'Bob', 'face_embedding': [0.9] * 128},
    ]

    call_count = 0
    def slow_get_all_students():
        nonlocal call_count
        call_count += 1
        time.sleep(0.05)
        return fake_students

    with patch('src.services.face_service.get_all_students', side_effect=slow_get_all_students):
        results = []
        def worker():
            model = get_trained_model()
            results.append(model)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        # All threads should get the same model dictionary
        for r in results:
            assert r is not None
            assert len(r['X']) == 2
        # DB should only be queried once despite 10 concurrent requests
        assert call_count == 1
