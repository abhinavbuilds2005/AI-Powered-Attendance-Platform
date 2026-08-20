import os
import io
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import numpy as np
from PIL import Image

from src.database.config import supabase
from src.database.db import (
    check_teacher_exists, create_teacher, teacher_login,
    get_all_students, create_student, get_student_subjects,
    get_student_attendance, enroll_student_to_subject,
    unenroll_student_to_subject, get_teacher_subjects,
    get_attendance_for_teacher, create_attendance
)
from src.pipelines.face_pipeline import predict_attendance, get_face_embeddings, train_classifier
from src.pipelines.voice_pipeline import get_voice_embedding, process_bulk_audio

app = FastAPI(
    title="AI Attendance API",
    description="Backend API for AI Attendance System supporting Face and Voice Recognition",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "time": datetime.utcnow().isoformat()}

# --- Student Endpoints ---

@app.post("/api/student/login-face")
async def student_login_face(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert('RGB')
        image_np = np.array(image)
        
        detected, all_ids, num_faces = predict_attendance(image_np)
        
        if num_faces == 0:
            raise HTTPException(status_code=400, detail="No face detected. Please center your face in the camera.")
        if num_faces > 1:
            raise HTTPException(status_code=400, detail="Multiple faces detected. Please make sure only one face is visible.")
        
        if detected:
            student_id = int(list(detected.keys())[0])
            all_students = get_all_students()
            student = next((s for s in all_students if s['student_id'] == student_id), None)
            
            if student:
                # Remove embedding float lists to keep payload small
                student_clean = student.copy()
                student_clean.pop('face_embedding', None)
                student_clean.pop('voice_embedding', None)
                return {"success": True, "student": student_clean}
                
        return {"success": False, "detail": "Face not recognized. If you are a new student, please register."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")

@app.post("/api/student/register")
async def student_register(
    name: str = Form(...),
    image: UploadFile = File(...),
    audio: Optional[UploadFile] = File(None)
):
    try:
        # Extract face embedding
        img_bytes = await image.read()
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        img_np = np.array(img)
        
        encodings = get_face_embeddings(img_np)
        if not encodings:
            raise HTTPException(status_code=400, detail="Could not capture facial features. Please ensure your face is fully visible.")
        face_emb = encodings[0].tolist()

        # Extract voice embedding if audio is provided
        voice_emb = None
        if audio:
            audio_bytes = await audio.read()
            voice_emb = get_voice_embedding(audio_bytes)

        response_data = create_student(name, face_embedding=face_emb, voice_embedding=voice_emb)
        if response_data:
            train_classifier()
            student = response_data[0]
            student_clean = student.copy()
            student_clean.pop('face_embedding', None)
            student_clean.pop('voice_embedding', None)
            return {"success": True, "student": student_clean}
            
        raise HTTPException(status_code=500, detail="Database insertion failed.")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.get("/api/student/{student_id}/dashboard")
async def student_dashboard_data(student_id: int):
    try:
        subjects = get_student_subjects(student_id)
        logs = get_student_attendance(student_id)
        return {"subjects": subjects, "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/student/{student_id}/available-subjects")
async def student_available_subjects(student_id: int):
    try:
        # Fetch all subjects
        all_subs_res = supabase.table('subjects').select("*, teachers(name)").execute()
        all_subs = all_subs_res.data
        # Fetch enrolled subjects
        enrolled = get_student_subjects(student_id)
        enrolled_ids = {sub['subject_id'] for sub in enrolled}
        # Filter available subjects
        available = [sub for sub in all_subs if sub['subject_id'] not in enrolled_ids]
        return available
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/student/enroll")
async def student_enroll(req: EnrollRequest):
    try:
        res = enroll_student_to_subject(req.student_id, req.subject_id)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/student/unenroll")
async def student_unenroll(req: EnrollRequest):
    try:
        res = unenroll_student_to_subject(req.student_id, req.subject_id)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Teacher Endpoints ---

@app.post("/api/teacher/register")
async def teacher_register_api(req: TeacherRegisterRequest):
    try:
        if check_teacher_exists(req.username):
            raise HTTPException(status_code=400, detail="Username already taken.")
        res = create_teacher(req.username, req.password, req.name)
        if res:
            return {"success": True, "detail": "Account created successfully. You can now log in."}
        raise HTTPException(status_code=500, detail="Database insertion failed.")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/teacher/login")
async def teacher_login_api(req: TeacherLoginRequest):
    try:
        teacher = teacher_login(req.username, req.password)
        if teacher:
            teacher_clean = teacher.copy()
            teacher_clean.pop('password', None)
            return {"success": True, "teacher": teacher_clean}
        raise HTTPException(status_code=400, detail="Invalid username or password.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/teacher/{teacher_id}/subjects")
async def teacher_subjects_api(teacher_id: int):
    try:
        subs = get_teacher_subjects(teacher_id)
        return subs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/teacher/subjects/create")
async def teacher_create_subject_api(req: CreateSubjectRequest):
    try:
        res = create_subject(req.subject_code, req.name, req.section, req.teacher_id)
        return {"success": True, "subject": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/teacher/{teacher_id}/attendance")
async def teacher_attendance_records_api(teacher_id: int):
    try:
        records = get_attendance_for_teacher(teacher_id)
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/teacher/take-attendance-face")
async def teacher_take_attendance_face(
    subject_id: int = Form(...),
    files: List[UploadFile] = File(...)
):
    try:
        all_detected_ids = {}
        for idx, file in enumerate(files):
            contents = await file.read()
            img = Image.open(io.BytesIO(contents)).convert('RGB')
            img_np = np.array(img)
            
            detected, _, _ = predict_attendance(img_np)
            if detected:
                for sid in detected.keys():
                    student_id = int(sid)
                    all_detected_ids.setdefault(student_id, []).append(file.filename or f"Photo {idx+1}")

        # Fetch all students enrolled in this subject
        enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', subject_id).execute()
        enrolled_students = enrolled_res.data

        results = []
        if enrolled_students:
            for node in enrolled_students:
                student = node['students']
                sources = all_detected_ids.get(int(student['student_id']), [])
                is_present = len(sources) > 0
                results.append({
                    "student_id": student['student_id'],
                    "name": student['name'],
                    "sources": sources,
                    "is_present": is_present
                })
        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Face analysis failed: {str(e)}")

@app.post("/api/teacher/take-attendance-voice")
async def teacher_take_attendance_voice(
    subject_id: int = Form(...),
    audio: UploadFile = File(...)
):
    try:
        # Fetch all students enrolled in this subject
        enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', subject_id).execute()
        enrolled_students = enrolled_res.data

        candidates_dict = {}
        if enrolled_students:
            for node in enrolled_students:
                student = node['students']
                if student.get('voice_embedding'):
                    candidates_dict[student['student_id']] = np.array(student['voice_embedding'])

        audio_bytes = await audio.read()
        detected_voices = process_bulk_audio(audio_bytes, candidates_dict)

        results = []
        if enrolled_students:
            for node in enrolled_students:
                student = node['students']
                student_id = student['student_id']
                is_present = student_id in detected_voices
                score = detected_voices.get(student_id, 0.0)
                results.append({
                    "student_id": student_id,
                    "name": student['name'],
                    "is_present": is_present,
                    "confidence": float(score) if is_present else 0.0
                })
        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice analysis failed: {str(e)}")

@app.post("/api/teacher/save-attendance")
async def teacher_save_attendance_api(logs: List[AttendanceLogItem]):
    try:
        logs_dict = [log.model_dump() for log in logs]
        res = create_attendance(logs_dict)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save attendance: {str(e)}")
