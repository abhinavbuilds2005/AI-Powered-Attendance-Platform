import io
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import List
from PIL import Image
import numpy as np

from src.schemas.schemas import TeacherRegisterRequest, TeacherLoginRequest, CreateSubjectRequest, AttendanceLogItem
from src.services.db_service import (
    check_teacher_exists, create_teacher, teacher_login,
    get_teacher_subjects, create_subject, get_attendance_for_teacher,
    create_attendance, supabase
)
from src.services.face_service import predict_attendance
from src.services.voice_service import process_bulk_audio

router = APIRouter(prefix="/teacher", tags=["Teacher"])

@router.post("/register")
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

@router.post("/login")
async def teacher_login_api(req: TeacherLoginRequest):
    try:
        teacher = teacher_login(req.username, req.password)
        if teacher:
            teacher_clean = teacher.copy()
            teacher_clean.pop('password', None)
            return {"success": True, "teacher": teacher_clean}
        raise HTTPException(status_code=400, detail="Invalid username or password.")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{teacher_id}/subjects")
async def teacher_subjects_api(teacher_id: int):
    try:
        subs = get_teacher_subjects(teacher_id)
        return subs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/subjects/create")
async def teacher_create_subject_api(req: CreateSubjectRequest):
    try:
        res = create_subject(req.subject_code, req.name, req.section, req.teacher_id)
        subject = res[0] if res else {}
        return {"success": True, "subject": subject}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{teacher_id}/attendance")
async def teacher_attendance_records_api(teacher_id: int):
    try:
        records = get_attendance_for_teacher(teacher_id)
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/take-attendance-face")
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

@router.post("/take-attendance-voice")
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

@router.post("/save-attendance")
async def teacher_save_attendance_api(logs: List[AttendanceLogItem]):
    try:
        logs_dict = [log.model_dump() for log in logs]
        res = create_attendance(logs_dict)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save attendance: {str(e)}")
