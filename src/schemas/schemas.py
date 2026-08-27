from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict, Union


class StudentRegisterRequest(BaseModel):
    name: str
    image: str
    audio: Optional[str] = None


class StudentFaceLoginRequest(BaseModel):
    images: Optional[List[str]] = None
    image: Optional[str] = None


class StudentVoiceLoginRequest(BaseModel):
    audio: str
    target_student: Optional[str] = None
    target_explicit: Optional[bool] = False


class StudentEnrollRequest(BaseModel):
    student_id: int
    subject_code: Optional[str] = None
    subject_id: Optional[int] = None


class StudentUnenrollRequest(BaseModel):
    student_id: int
    subject_id: int


# Backward compatibility alias
class EnrollRequest(BaseModel):
    student_id: int
    subject_id: Optional[int] = None
    subject_code: Optional[str] = None


class TeacherRegisterRequest(BaseModel):
    username: str
    password: str
    name: str


class TeacherLoginRequest(BaseModel):
    username: str
    password: str


class CreateSubjectRequest(BaseModel):
    subject_code: str
    name: str
    section: str
    teacher_id: int


class FaceScanRequest(BaseModel):
    subject_id: int
    images: List[str]


class VoiceScanRequest(BaseModel):
    subject_id: int
    audio: str


class AttendanceLogItem(BaseModel):
    student_id: int
    subject_id: int
    timestamp: str
    is_present: bool


class CommitAttendanceRequest(BaseModel):
    logs: List[AttendanceLogItem]


class StudentCheckInRequest(BaseModel):
    student_id: int
    subject_id: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_label: Optional[str] = None
    is_remote: Optional[bool] = False

