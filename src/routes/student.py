import io
import numpy as np
from PIL import Image
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List

from src.schemas.schemas import (
    StudentRegisterRequest,
    StudentFaceLoginRequest,
    StudentVoiceLoginRequest,
    StudentEnrollRequest,
    StudentUnenrollRequest,
    EnrollRequest
)
from src.services.db_service import (
    get_all_students, create_student, get_student_subjects,
    get_student_attendance, enroll_student_to_subject,
    unenroll_student_to_subject, supabase
)
from src.services.face_service import (
    predict_attendance, get_face_embeddings, train_classifier,
    verify_liveness_and_anti_spoof
)
from src.services.voice_service import get_voice_embedding, identify_speaker
from src.core.utils import decode_base64_image, decode_base64_audio

router = APIRouter(prefix="/student", tags=["Student"])


@router.post("/register")
def student_register(req: StudentRegisterRequest):
    """Register a new student with face and optional voice biometrics."""
    try:
        name = req.name.strip() if req.name else ""
        if not name:
            raise HTTPException(status_code=400, detail="Please enter your full official name.")

        if not req.image:
            raise HTTPException(status_code=400, detail="Face photo is required for biometric registration.")

        # Extract face embedding
        try:
            img_np = decode_base64_image(req.image)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid face photo data: {str(e)}")

        encodings = get_face_embeddings(img_np)
        if len(encodings) > 1:
            raise HTTPException(status_code=400, detail="Multiple faces detected in viewfinder. Please ensure only your face is visible.")
        if not encodings:
            raise HTTPException(status_code=400, detail="Could not capture facial features. Please ensure your face is well-lit and facing the camera.")
        
        face_emb = encodings[0].tolist()

        # Extract voice embedding if audio is provided
        voice_emb = None
        if req.audio and len(str(req.audio).strip()) > 100:
            try:
                audio_bytes = decode_base64_audio(req.audio)
                voice_emb = get_voice_embedding(audio_bytes)
                if voice_emb:
                    print(f"[Register] Successfully extracted 256-D voice embedding for {name}")
                else:
                    print(f"[Register] Voice sample provided but could not extract clean embedding for {name}")
            except Exception as e:
                print("[Register] Voice embedding extraction notice:", e)
                voice_emb = None

        response_data = create_student(name, face_embedding=face_emb, voice_embedding=voice_emb)
        if response_data:
            train_classifier()
            student = response_data[0]
            student_clean = student.copy()
            student_clean.pop('face_embedding', None)
            student_clean.pop('voice_embedding', None)
            
            voice_status_msg = " and voiceprint" if voice_emb else ""
            return {
                "success": True,
                "message": f"Biometric profile created successfully for {name}{voice_status_msg}!",
                "student": student_clean
            }

        raise HTTPException(status_code=500, detail="Database insertion failed.")
    except HTTPException as he:
        raise he
    except Exception as e:
        print("[Register] Unexpected error:", e)
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/face-login")
@router.post("/login-face")
def student_face_login(req: StudentFaceLoginRequest):
    """Authenticate a student using face recognition and burst capture with live anti-spoofing."""
    try:
        frames = req.images if req.images else ([req.image] if req.image else [])
        if not frames:
            raise HTTPException(status_code=400, detail="No face images provided for scan.")

        decoded_images = []
        for frame_b64 in frames:
            try:
                decoded_images.append(decode_base64_image(frame_b64))
            except Exception:
                continue

        if not decoded_images:
            raise HTTPException(status_code=400, detail="Could not decode face image frames.")

        # If multiple burst frames are sent (standard FaceID flow), perform Anti-Spoofing check
        if len(decoded_images) >= 2:
            is_live, liveness_msg = verify_liveness_and_anti_spoof(decoded_images)
            if not is_live:
                print("[Anti-Spoofing Alert] Rejected static photo / screen presentation attack:", liveness_msg)
                return {
                    "success": False,
                    "status": "spoof_detected",
                    "message": liveness_msg
                }

        matched_student = None
        all_students = get_all_students()

        for img_np in decoded_images:
            try:
                detected, all_ids, num_faces = predict_attendance(img_np)
                if detected:
                    student_id = int(list(detected.keys())[0])
                    matched = next((s for s in all_students if s['student_id'] == student_id), None)
                    if matched:
                        matched_student = matched
                        break
            except Exception:
                continue

        if matched_student:
            student_clean = matched_student.copy()
            student_clean.pop('face_embedding', None)
            student_clean.pop('voice_embedding', None)
            return {
                "success": True,
                "student": student_clean,
                "message": f"Welcome back, {student_clean['name']}!"
            }

        return {
            "success": False,
            "status": "unrecognized",
            "message": "Face not recognized. If you are a new student, please register."
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")


@router.post("/voice-login")
def student_voice_login(req: StudentVoiceLoginRequest):
    """Authenticate a student using voice biometrics."""
    try:
        if not req.audio:
            raise HTTPException(status_code=400, detail="No audio sample provided.")

        try:
            audio_bytes = decode_base64_audio(req.audio)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid audio sample format.")

        voice_emb = get_voice_embedding(audio_bytes)
        if not voice_emb:
            return {
                "success": False,
                "message": "Could not extract voice features. Please speak clearly into the microphone."
            }

        all_students = get_all_students() or []
        candidates_dict = {
            s['student_id']: np.array(s['voice_embedding'])
            for s in all_students
            if s.get('voice_embedding') is not None
        }

        if not candidates_dict:
            return {
                "success": False,
                "message": "No students with enrolled voiceprints found yet. Please register or enroll your voice sample."
            }

        target_name = (req.target_student or "").strip().lower()
        matched_student = None
        best_score = 0.0

        # If a target student was explicitly specified or spoken, prioritize 1:1 check
        if target_name:
            target_candidates = [
                s for s in all_students 
                if (target_name in s.get('name', '').lower() or str(s.get('student_id')) == target_name)
                and s.get('voice_embedding') is not None
            ]
            if target_candidates:
                target_dict = {s['student_id']: np.array(s['voice_embedding']) for s in target_candidates}
                matched_sid, score = identify_speaker(np.array(voice_emb), target_dict, threshold=0.40)
                if matched_sid:
                    matched_student = next((s for s in target_candidates if s['student_id'] == matched_sid), None)
                    best_score = score

        # If not matched via target, perform 1:N open biometric search
        if not matched_student:
            matched_sid, score = identify_speaker(np.array(voice_emb), candidates_dict, threshold=0.45)
            if matched_sid:
                matched_student = next((s for s in all_students if s['student_id'] == matched_sid), None)
                best_score = score

        if matched_student:
            student_clean = matched_student.copy()
            student_clean.pop('face_embedding', None)
            student_clean.pop('voice_embedding', None)
            return {
                "success": True,
                "student": student_clean,
                "confidence": float(best_score),
                "message": f"Welcome back, {student_clean['name']}!"
            }

        return {
            "success": False,
            "message": "Voice sample did not match any enrolled student. Please try speaking closer to the microphone."
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice login error: {str(e)}")


@router.get("/{student_id}/courses")
async def get_student_courses(student_id: int):
    """Retrieve enrolled courses with session attendance statistics and rates for a student."""
    try:
        enrollments = get_student_subjects(student_id)
        courses = []
        for enr in enrollments:
            sub = enr.get('subjects')
            if not sub:
                continue
            subject_id = sub['subject_id']
            logs_res = supabase.table('attendance_logs').select('*').eq('subject_id', subject_id).execute()
            all_logs = logs_res.data or []
            
            session_timestamps = set(l['timestamp'] for l in all_logs)
            total_sessions = len(session_timestamps)
            
            student_attended = len([
                l for l in all_logs
                if l.get('student_id') == student_id and l.get('is_present')
            ])
            
            rate = round((student_attended / total_sessions) * 100) if total_sessions > 0 else 100
            
            courses.append({
                "subject_id": subject_id,
                "name": sub['name'],
                "subject_code": sub['subject_code'],
                "section": sub['section'],
                "attended_sessions": student_attended,
                "total_sessions": total_sessions,
                "attendance_rate": rate
            })
        return {"courses": courses}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{student_id}/dashboard")
async def student_dashboard_data(student_id: int):
    """Retrieve dashboard data for a student."""
    try:
        subjects = get_student_subjects(student_id)
        logs = get_student_attendance(student_id)
        return {"subjects": subjects, "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{student_id}/available-subjects")
async def student_available_subjects(student_id: int):
    """Retrieve all subjects available for enrollment."""
    try:
        all_subs_res = supabase.table('subjects').select("*, teachers(name)").execute()
        all_subs = all_subs_res.data or []
        enrolled = get_student_subjects(student_id)
        enrolled_ids = {sub['subject_id'] for sub in enrolled if 'subject_id' in sub}
        available = [sub for sub in all_subs if sub['subject_id'] not in enrolled_ids]
        return available
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enroll")
async def student_enroll(req: StudentEnrollRequest):
    """Enroll student into a subject via subject code or subject ID."""
    try:
        subject_id = req.subject_id
        subject_name = "Course"
        if not subject_id and req.subject_code:
            code = req.subject_code.strip()
            sub_res = supabase.table('subjects').select('*').ilike('subject_code', code).execute()
            if not sub_res.data:
                raise HTTPException(status_code=404, detail=f"Course with code '{code}' not found.")
            subject_id = sub_res.data[0]['subject_id']
            subject_name = sub_res.data[0]['name']
        elif subject_id:
            sub_res = supabase.table('subjects').select('*').eq('subject_id', subject_id).execute()
            if sub_res.data:
                subject_name = sub_res.data[0]['name']
        else:
            raise HTTPException(status_code=400, detail="Please enter a valid course code.")

        existing = supabase.table('subject_students').select('*').eq('student_id', req.student_id).eq('subject_id', subject_id).execute()
        if existing.data:
            return {"success": True, "message": f"You are already enrolled in {subject_name}!"}

        res = enroll_student_to_subject(req.student_id, subject_id)
        return {"success": True, "message": f"Successfully enrolled in {subject_name}!", "data": res}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unenroll")
async def student_unenroll(req: StudentUnenrollRequest):
    """Unenroll student from a subject."""
    try:
        res = unenroll_student_to_subject(req.student_id, req.subject_id)
        return {"success": True, "message": "Successfully unenrolled from course.", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
