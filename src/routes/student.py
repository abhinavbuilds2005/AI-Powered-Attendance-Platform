import io
import numpy as np
from PIL import Image
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional

from src.schemas.schemas import EnrollRequest
from src.services.db_service import (
    get_all_students, create_student, get_student_subjects,
    get_student_attendance, enroll_student_to_subject,
    unenroll_student_to_subject, supabase
)
from src.services.face_service import predict_attendance, get_face_embeddings, train_classifier
from src.services.voice_service import get_voice_embedding

router = APIRouter(prefix="/student", tags=["Student"])

@router.post("/login-face")
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

@router.post("/register")
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
        if len(encodings) > 1:
            raise HTTPException(status_code=400, detail="Multiple faces detected. Please submit a photo containing only you.")
        if not encodings:
            raise HTTPException(status_code=400, detail="Could not capture facial features. Please ensure your face is fully visible.")
        face_emb = encodings[0].tolist()

        # Extract voice embedding if audio is provided
        voice_emb = None
        if audio:
            audio_bytes = await audio.read()
            voice_emb = get_voice_embedding(audio_bytes)
            if not voice_emb:
                raise HTTPException(status_code=400, detail="Could not process the voice recording. Please record a clear phrase and try again.")

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

@router.get("/{student_id}/dashboard")
async def student_dashboard_data(student_id: int):
    try:
        subjects = get_student_subjects(student_id)
        logs = get_student_attendance(student_id)
        return {"subjects": subjects, "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{student_id}/available-subjects")
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

@router.post("/enroll")
async def student_enroll(req: EnrollRequest):
    try:
        res = enroll_student_to_subject(req.student_id, req.subject_id)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/unenroll")
async def student_unenroll(req: EnrollRequest):
    try:
        res = unenroll_student_to_subject(req.student_id, req.subject_id)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
