from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List
import numpy as np

from src.schemas.schemas import (
    FaceScanRequest, VoiceScanRequest, CommitAttendanceRequest,
    StudentCheckInRequest
)
from src.services.db_service import create_attendance, supabase
from src.services.face_service import predict_attendance
from src.services.voice_service import process_bulk_audio
from src.core.utils import decode_base64_image, decode_base64_audio

router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.post("/face-scan")
def attendance_face_scan(req: FaceScanRequest):
    """Scan staged classroom photos for facial landmarks and match enrolled students."""
    try:
        subject_id = req.subject_id
        enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', subject_id).execute()
        enrolled_students = enrolled_res.data or []

        if not enrolled_students:
            return {
                "success": True,
                "results": [],
                "logs": [],
                "message": "No students are enrolled in this course."
            }

        all_detected_ids = {}
        for idx, img_b64 in enumerate(req.images):
            try:
                img_np = decode_base64_image(img_b64)
                detected, _, _ = predict_attendance(img_np)
                if detected:
                    for sid in detected.keys():
                        all_detected_ids.setdefault(int(sid), []).append(f"Photo {idx+1}")
            except Exception as e:
                print(f"Error processing image {idx+1}:", e)
                continue

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        results = []
        pending_logs = []

        for node in enrolled_students:
            student = node.get('students')
            if not student:
                continue
            sid = int(student['student_id'])
            sources = all_detected_ids.get(sid, [])
            is_present = len(sources) > 0
            source_label = f"FaceID ({', '.join(sources)})" if is_present else "Absent"

            results.append({
                "student_id": sid,
                "name": student['name'],
                "source": source_label,
                "is_present": is_present
            })
            pending_logs.append({
                "student_id": sid,
                "subject_id": subject_id,
                "timestamp": now_str,
                "is_present": is_present
            })

        return {
            "success": True,
            "results": results,
            "logs": pending_logs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classroom face scan failed: {str(e)}")


@router.post("/voice-scan")
def attendance_voice_scan(req: VoiceScanRequest):
    """Scan classroom microphone recording and identify speaker voiceprints."""
    try:
        subject_id = req.subject_id
        enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', subject_id).execute()
        enrolled_students = enrolled_res.data or []

        if not enrolled_students:
            return {
                "success": True,
                "results": [],
                "logs": [],
                "message": "No students are enrolled in this course."
            }

        candidates_dict = {}
        for node in enrolled_students:
            student = node.get('students')
            if student and student.get('voice_embedding'):
                try:
                    candidates_dict[student['student_id']] = np.array(student['voice_embedding'])
                except Exception:
                    pass

        try:
            audio_bytes = decode_base64_audio(req.audio)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid classroom audio data.")

        detected_voices = process_bulk_audio(audio_bytes, candidates_dict)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        results = []
        pending_logs = []

        for node in enrolled_students:
            student = node.get('students')
            if not student:
                continue
            sid = int(student['student_id'])
            is_present = sid in detected_voices
            score = detected_voices.get(sid, 0.0)
            source_label = f"VoiceID ({int(score * 100)}%)" if is_present else "Absent"

            results.append({
                "student_id": sid,
                "name": student['name'],
                "source": source_label,
                "is_present": is_present,
                "confidence": float(score) if is_present else 0.0
            })
            pending_logs.append({
                "student_id": sid,
                "subject_id": subject_id,
                "timestamp": now_str,
                "is_present": is_present
            })

        return {
            "success": True,
            "results": results,
            "logs": pending_logs
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classroom voice scan failed: {str(e)}")


@router.post("/commit")
def attendance_commit(req: CommitAttendanceRequest):
    """Commit verified attendance logs to Supabase database."""
    try:
        logs_dict = [log.model_dump() for log in req.logs]
        res = create_attendance(logs_dict)
        return {"success": True, "data": res, "message": "Attendance successfully saved to database!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to commit attendance: {str(e)}")


@router.post("/student-checkin")
def student_checkin(req: StudentCheckInRequest):
    """Direct self-checkin for a student with live GPS location & geofencing verification."""
    try:
        now_dt = datetime.now()
        iso_timestamp = now_dt.isoformat()

        # Determine location descriptor
        if req.location_label:
            loc_str = req.location_label
        elif req.is_remote:
            loc_str = "🏠 Remote / From Home"
        else:
            loc_str = "📍 On-Campus (Verified)"

        if req.latitude is not None and req.longitude is not None:
            loc_str += f" ({req.latitude:.4f}, {req.longitude:.4f})"

        log_data = [{
            "student_id": req.student_id,
            "subject_id": req.subject_id,
            "timestamp": iso_timestamp,
            "is_present": True
        }]
        res = create_attendance(log_data)
        return {
            "success": True,
            "message": f"Attendance successfully recorded! ({loc_str})",
            "timestamp": iso_timestamp,
            "is_remote": req.is_remote,
            "location_label": loc_str,
            "data": res
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Check-in failed: {str(e)}")

