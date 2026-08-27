import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.app import app
from src.services.face_service import invalidate_classifier_cache

client = TestClient(app)

# Helper to create a dummy valid base64 image
DUMMY_BASE64_IMAGE = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="


@pytest.fixture(autouse=True)
def reset_cache():
    invalidate_classifier_cache()
    yield
    invalidate_classifier_cache()


def test_student_registration_success_without_sync_training():
    """Verify that student registration succeeds, calls create_student and invalidates cache without train_classifier."""
    fake_face_emb = np.array([0.15] * 128)
    created_student = [{'student_id': 1, 'name': 'John Doe', 'face_embedding': fake_face_emb.tolist(), 'voice_embedding': None}]

    with patch('src.routes.student.decode_base64_image', return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
         patch('src.routes.student.get_face_embeddings', return_value=[fake_face_emb]), \
         patch('src.routes.student.create_student', return_value=created_student) as mock_create, \
         patch('src.routes.student.invalidate_classifier_cache') as mock_invalidate, \
         patch('src.services.face_service.train_classifier') as mock_train_classifier:

        payload = {
            "name": "John Doe",
            "image": DUMMY_BASE64_IMAGE,
            "audio": None
        }

        response = client.post("/api/student/register", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["student"]["name"] == "John Doe"
        assert data["student"]["student_id"] == 1
        assert "face_embedding" not in data["student"]

        # Check that DB insertion was called
        mock_create.assert_called_once()
        # Check that cache invalidation was called
        mock_invalidate.assert_called_once()
        # Check that synchronous train_classifier was NOT called
        mock_train_classifier.assert_not_called()


def test_student_registration_with_voice():
    """Verify registration succeeds when valid audio is provided."""
    fake_face_emb = np.array([0.2] * 128)
    fake_voice_emb = [0.05] * 256
    created_student = [{'student_id': 2, 'name': 'Jane Doe', 'face_embedding': fake_face_emb.tolist(), 'voice_embedding': fake_voice_emb}]

    with patch('src.routes.student.decode_base64_image', return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
         patch('src.routes.student.get_face_embeddings', return_value=[fake_face_emb]), \
         patch('src.routes.student.decode_base64_audio', return_value=b'dummy_audio_bytes'), \
         patch('src.routes.student.get_voice_embedding', return_value=fake_voice_emb), \
         patch('src.routes.student.create_student', return_value=created_student) as mock_create, \
         patch('src.routes.student.invalidate_classifier_cache'):

        payload = {
            "name": "Jane Doe",
            "image": DUMMY_BASE64_IMAGE,
            "audio": "data:audio/wav;base64," + "A" * 200
        }

        response = client.post("/api/student/register", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "voiceprint" in data["message"].lower()


def test_student_registration_validation_empty_name():
    """Validation: empty or missing name returns 400."""
    payload = {
        "name": "   ",
        "image": DUMMY_BASE64_IMAGE,
        "audio": None
    }
    response = client.post("/api/student/register", json=payload)
    assert response.status_code == 400
    assert "official name" in response.json()["detail"].lower()


def test_student_registration_validation_no_image():
    """Validation: missing image returns 400."""
    payload = {
        "name": "John Doe",
        "image": "",
        "audio": None
    }
    response = client.post("/api/student/register", json=payload)
    assert response.status_code == 400
    assert "photo is required" in response.json()["detail"].lower()


def test_student_registration_validation_no_face_detected():
    """Validation: no face detected in photo returns 400."""
    with patch('src.routes.student.decode_base64_image', return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
         patch('src.routes.student.get_face_embeddings', return_value=[]):

        payload = {
            "name": "John Doe",
            "image": DUMMY_BASE64_IMAGE,
            "audio": None
        }
        response = client.post("/api/student/register", json=payload)
        assert response.status_code == 400
        assert "could not capture facial features" in response.json()["detail"].lower()


def test_student_registration_validation_multiple_faces_detected():
    """Validation: multiple faces detected in photo returns 400."""
    emb1 = np.zeros(128)
    emb2 = np.zeros(128)
    with patch('src.routes.student.decode_base64_image', return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
         patch('src.routes.student.get_face_embeddings', return_value=[emb1, emb2]):

        payload = {
            "name": "John Doe",
            "image": DUMMY_BASE64_IMAGE,
            "audio": None
        }
        response = client.post("/api/student/register", json=payload)
        assert response.status_code == 400
        assert "multiple faces" in response.json()["detail"].lower()


def test_student_registration_db_failure_handling():
    """Validation: database insertion failure returns 500 without crashing."""
    fake_face_emb = np.array([0.15] * 128)
    with patch('src.routes.student.decode_base64_image', return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
         patch('src.routes.student.get_face_embeddings', return_value=[fake_face_emb]), \
         patch('src.routes.student.create_student', return_value=[]):

        payload = {
            "name": "John Doe",
            "image": DUMMY_BASE64_IMAGE,
            "audio": None
        }
        response = client.post("/api/student/register", json=payload)
        assert response.status_code == 500
        assert "database insertion failed" in response.json()["detail"].lower()


def test_two_sequential_registrations_and_face_login():
    """Test two students registering sequentially, followed by face login."""
    alice_emb = np.array([0.1] * 128)
    bob_emb = np.array([0.9] * 128)

    db_students = []

    def mock_create(name, face_embedding=None, voice_embedding=None):
        sid = len(db_students) + 1
        rec = {'student_id': sid, 'name': name, 'face_embedding': face_embedding, 'voice_embedding': voice_embedding}
        db_students.append(rec)
        return [rec]

    with patch('src.routes.student.decode_base64_image', return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
         patch('src.routes.student.create_student', side_effect=mock_create), \
         patch('src.routes.student.get_all_students', side_effect=lambda: list(db_students)), \
         patch('src.services.face_service.get_all_students', side_effect=lambda: list(db_students)):

        # Register Alice
        with patch('src.routes.student.get_face_embeddings', return_value=[alice_emb]):
            res1 = client.post("/api/student/register", json={"name": "Alice", "image": DUMMY_BASE64_IMAGE})
            assert res1.status_code == 200
            assert res1.json()["student"]["name"] == "Alice"

        # Register Bob
        with patch('src.routes.student.get_face_embeddings', return_value=[bob_emb]):
            res2 = client.post("/api/student/register", json={"name": "Bob", "image": DUMMY_BASE64_IMAGE})
            assert res2.status_code == 200
            assert res2.json()["student"]["name"] == "Bob"

        assert len(db_students) == 2

        # Test Face Login for Alice
        with patch('src.services.face_service.get_face_embeddings', return_value=[alice_emb]):
            login_res = client.post("/api/student/face-login", json={"images": [DUMMY_BASE64_IMAGE]})
            assert login_res.status_code == 200
            login_data = login_res.json()
            assert login_data["success"] is True
            assert login_data["student"]["name"] == "Alice"

        # Test Face Login for Bob
        with patch('src.services.face_service.get_face_embeddings', return_value=[bob_emb]):
            login_res_bob = client.post("/api/student/face-login", json={"images": [DUMMY_BASE64_IMAGE]})
            assert login_res_bob.status_code == 200
            login_data_bob = login_res_bob.json()
            assert login_data_bob["success"] is True
            assert login_data_bob["student"]["name"] == "Bob"
