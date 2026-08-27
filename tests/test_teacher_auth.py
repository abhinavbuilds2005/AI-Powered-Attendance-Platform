import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)


def test_teacher_registration_success():
    """Test teacher registration via /api/auth/teacher/register."""
    created_teacher = [{'teacher_id': 1, 'username': 'prof_smith', 'name': 'Prof Smith'}]

    with patch('src.routes.common.check_teacher_exists', return_value=False), \
         patch('src.routes.common.create_teacher', return_value=created_teacher):

        payload = {
            "name": "Prof Smith",
            "username": "prof_smith",
            "password": "secretpassword123"
        }
        res = client.post("/api/auth/teacher/register", json=payload)
        assert res.status_code == 200
        assert res.json()["success"] is True


def test_teacher_registration_duplicate_username():
    """Test teacher registration with existing username returns 400."""
    with patch('src.routes.common.check_teacher_exists', return_value=True):
        payload = {
            "name": "Prof Smith",
            "username": "prof_smith",
            "password": "secretpassword123"
        }
        res = client.post("/api/auth/teacher/register", json=payload)
        assert res.status_code == 400
        assert "already taken" in res.json()["detail"].lower()


def test_teacher_login_success():
    """Test teacher login with correct credentials."""
    teacher_record = {'teacher_id': 1, 'username': 'prof_smith', 'name': 'Prof Smith', 'password': 'hashed_pass'}

    with patch('src.routes.common.teacher_login', return_value=teacher_record):
        payload = {
            "username": "prof_smith",
            "password": "secretpassword123"
        }
        res = client.post("/api/auth/teacher/login", json=payload)
        assert res.status_code == 200
        assert res.json()["success"] is True
        assert res.json()["teacher"]["name"] == "Prof Smith"
        assert "password" not in res.json()["teacher"]


def test_teacher_login_invalid_credentials():
    """Test teacher login with invalid credentials returns 400."""
    with patch('src.routes.common.teacher_login', return_value=None):
        payload = {
            "username": "prof_smith",
            "password": "wrongpassword"
        }
        res = client.post("/api/auth/teacher/login", json=payload)
        assert res.status_code == 400
        assert "invalid" in res.json()["detail"].lower()
