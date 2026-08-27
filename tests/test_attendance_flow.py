import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)


def test_attendance_face_scan_empty_course():
    """Test attendance face scan when no students are enrolled in course."""
    mock_supabase_res = MagicMock()
    mock_supabase_res.data = []

    with patch('src.routes.attendance.supabase') as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_supabase_res

        payload = {
            "subject_id": 99,
            "images": ["data:image/jpeg;base64,dummy"]
        }
        res = client.post("/api/attendance/face-scan", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["results"] == []
        assert "no students are enrolled" in data["message"].lower()


def test_attendance_face_scan_matching():
    """Test attendance face scan accurately recognizes enrolled student."""
    enrolled_node = [{
        'students': {
            'student_id': 101,
            'name': 'Alice'
        }
    }]
    mock_supabase_res = MagicMock()
    mock_supabase_res.data = enrolled_node

    with patch('src.routes.attendance.supabase') as mock_sb, \
         patch('src.routes.attendance.decode_base64_image', return_value=np.zeros((10, 10, 3))), \
         patch('src.routes.attendance.predict_attendance', return_value=({101: True}, [101], 1)):

        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_supabase_res

        payload = {
            "subject_id": 1,
            "images": ["data:image/jpeg;base64,dummy"]
        }
        res = client.post("/api/attendance/face-scan", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert len(data["results"]) == 1
        assert data["results"][0]["student_id"] == 101
        assert data["results"][0]["is_present"] is True
        assert "FaceID" in data["results"][0]["source"]


def test_attendance_commit():
    """Test committing attendance logs to database."""
    with patch('src.routes.attendance.create_attendance', return_value=[{"log_id": 1}]):
        payload = {
            "logs": [
                {
                    "student_id": 101,
                    "subject_id": 1,
                    "timestamp": "2026-08-27 10:00",
                    "is_present": True
                }
            ]
        }
        res = client.post("/api/attendance/commit", json=payload)
        assert res.status_code == 200
        assert res.json()["success"] is True
