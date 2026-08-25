from typing import List, Dict, Any, Optional
from supabase import create_client, Client
from src.core.config import settings
from src.core.security import hash_pass, check_pass

# Initialize Supabase client
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

def check_teacher_exists(username: str) -> bool:
    """Check if a teacher with the given username already exists."""
    response = supabase.table("teachers").select("username").eq("username", username).execute()
    return len(response.data) > 0

def create_teacher(username: str, password: str, name: str) -> List[Dict[str, Any]]:
    """Create a new teacher in the database."""
    data = {
        "username": username,
        "password": hash_pass(password),
        "name": name
    }
    response = supabase.table("teachers").insert(data).execute()
    return response.data

def teacher_login(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate a teacher. Returns the teacher record if valid, else None."""
    response = supabase.table("teachers").select("*").eq("username", username).execute()
    if response.data:
        teacher = response.data[0]
        if check_pass(password, teacher['password']):
            return teacher
    return None

def get_all_students() -> List[Dict[str, Any]]:
    """Retrieve all students registered in the database."""
    response = supabase.table('students').select("*").execute()
    return response.data

def create_student(
    name: str,
    face_embedding: Optional[List[float]] = None,
    voice_embedding: Optional[List[float]] = None
) -> List[Dict[str, Any]]:
    """Insert a new student with biometric embeddings into the database."""
    data = {
        "name": name,
        "face_embedding": face_embedding,
        "voice_embedding": voice_embedding
    }
    response = supabase.table('students').insert(data).execute()
    return response.data

def create_subject(
    subject_code: str,
    name: str,
    section: str,
    teacher_id: int
) -> List[Dict[str, Any]]:
    """Create a new subject assigned to a teacher."""
    data = {
        "subject_code": subject_code,
        "name": name,
        "section": section,
        "teacher_id": teacher_id
    }
    response = supabase.table("subjects").insert(data).execute()
    return response.data

def get_teacher_subjects(teacher_id: int) -> List[Dict[str, Any]]:
    """Retrieve all subjects taught by a teacher, alongside student and class counts."""
    response = supabase.table('subjects').select(
        "*, subject_students(count), attendance_logs(timestamp)"
    ).eq("teacher_id", teacher_id).execute()
    
    subjects = response.data
    for sub in subjects:
        sub['total_students'] = (
            sub.get("subject_students", [{}])[0].get('count', 0)
            if sub.get('subject_students')
            else 0
        )
        attendance = sub.get('attendance_logs', [])
        unique_sessions = len(set(log['timestamp'] for log in attendance))
        sub['total_classes'] = unique_sessions
        
        # Clean up relation artifacts
        sub.pop('subject_students', None)
        sub.pop('attendance_logs', None)
        
    return subjects

def enroll_student_to_subject(student_id: int, subject_id: int) -> List[Dict[str, Any]]:
    """Enroll a student into a subject."""
    data = {
        "student_id": student_id,
        "subject_id": subject_id
    }
    response = supabase.table('subject_students').insert(data).execute()
    return response.data

def unenroll_student_to_subject(student_id: int, subject_id: int) -> List[Dict[str, Any]]:
    """Remove a student enrollment from a subject."""
    response = supabase.table('subject_students').delete().eq(
        'student_id', student_id
    ).eq('subject_id', subject_id).execute()
    return response.data

def get_student_subjects(student_id: int) -> List[Dict[str, Any]]:
    """Get all subjects a student is enrolled in."""
    response = supabase.table('subject_students').select(
        '*, subjects(*)'
    ).eq('student_id', student_id).execute()
    return response.data

def get_student_attendance(student_id: int) -> List[Dict[str, Any]]:
    """Get complete attendance logs for a student."""
    response = supabase.table('attendance_logs').select(
        '*, subjects(*)'
    ).eq('student_id', student_id).execute()
    return response.data

def create_attendance(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bulk create attendance logs in the database."""
    response = supabase.table('attendance_logs').insert(logs).execute()
    return response.data

def get_attendance_for_teacher(teacher_id: int) -> List[Dict[str, Any]]:
    """Retrieve all attendance logs for classes taught by a specific teacher."""
    response = supabase.table('attendance_logs').select(
        "*, subjects!inner(*)"
    ).eq('subjects.teacher_id', teacher_id).execute()
    return response.data
