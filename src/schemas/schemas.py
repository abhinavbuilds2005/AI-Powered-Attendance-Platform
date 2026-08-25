from pydantic import BaseModel
from typing import List, Optional

class EnrollRequest(BaseModel):
    student_id: int
    subject_id: int

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

class AttendanceLogItem(BaseModel):
    student_id: int
    subject_id: int
    timestamp: str
    is_present: bool
