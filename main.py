import os
import io
import base64
import re
import asyncio
from datetime import datetime
from typing import List, Optional
import numpy as np
import pandas as pd
from PIL import Image, ImageOps
import segno

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Internal imports
from src.database.config import supabase
from src.database.db import (
    check_teacher_exists,
    create_teacher,
    teacher_login,
    get_all_students,
    create_student,
    update_student_voice_embedding,
    create_subject,
    get_teacher_subjects,
    enroll_student_to_subject,
    unenroll_student_to_subject,
    get_student_subjects,
    get_student_attendance,
    create_attendance,
    get_attendance_for_teacher,
)
from src.pipelines.face_pipeline import predict_attendance, get_face_embeddings, train_classifier
from src.pipelines.voice_pipeline import get_voice_embedding, process_bulk_audio, safe_get_voice_embedding

app = FastAPI(title="PresentAI API - Multimodal Biometric Attendance System", version="2.0.0")

# CORS middleware for development and deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static folder
os.makedirs("static", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

# ---------------------- Pydantic Request Models ---------------------- #
class TeacherAuthRequest(BaseModel):
    username: str
    password: str
    name: Optional[str] = None

class CreateSubjectRequest(BaseModel):
    subject_code: str
    name: str
    section: str
    teacher_id: int

class EnrollRequest(BaseModel):
    student_id: int
    subject_code: str

class UnenrollRequest(BaseModel):
    student_id: int
    subject_id: int

class AttendanceCommitRequest(BaseModel):
    logs: List[dict]


# ---------------------- Helper Utilities ---------------------- #
def decode_base64_image(base64_str: str) -> np.ndarray:
    if "," in base64_str:
        base64_str = base64_str.split(",")[1]
    image_bytes = base64.b64decode(base64_str)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = ImageOps.exif_transpose(image)

    max_side = 640
    width, height = image.size
    if max(width, height) > max_side:
        scale = max_side / max(width, height)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    return np.array(image)

def decode_base64_audio(base64_str: str) -> bytes:
    if "," in base64_str:
        base64_str = base64_str.split(",")[1]
    return base64.b64decode(base64_str)


# ---------------------- Root HTML Route ---------------------- #
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>PresentAI API is running. Please load static/index.html</h1>")


@app.head("/")
async def check_root():
    return Response(status_code=200)


# ---------------------- Teacher Auth Endpoints ---------------------- #
@app.post("/api/auth/teacher/register")
async def register_teacher_endpoint(req: TeacherAuthRequest):
    if not req.username or not req.password or not req.name:
        raise HTTPException(status_code=400, detail="All fields are required.")
    if check_teacher_exists(req.username.strip()):
        raise HTTPException(status_code=400, detail="Username is already taken.")
    
    try:
        created = create_teacher(req.username.strip(), req.password, req.name.strip())
        return {"success": True, "message": "Teacher account created successfully!", "data": created}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/teacher/login")
async def login_teacher_endpoint(req: TeacherAuthRequest):
    teacher = teacher_login(req.username.strip(), req.password)
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    # Exclude password hash from response
    teacher_safe = {k: v for k, v in teacher.items() if k != "password"}
    return {"success": True, "teacher": teacher_safe}


# ---------------------- Student Biometrics Endpoints ---------------------- #
@app.post("/api/student/face-login")
async def student_face_login(payload: dict):
    images_b64 = payload.get("images")
    single_image = payload.get("image")

    if not images_b64 and single_image:
        images_b64 = [single_image]

    if not images_b64:
        raise HTTPException(status_code=400, detail="Image frame is required.")

    # Decode burst frames
    images_np = [decode_base64_image(b64) for b64 in images_b64 if b64]

    if not images_np:
        return {"success": False, "status": "no_face", "message": "No valid frames received."}

    # Run 68-landmark Eye Aspect Ratio (EAR) Anti-Spoofing Check
    from src.pipelines.face_pipeline import verify_liveness_and_anti_spoof
    is_live, liveness_msg = verify_liveness_and_anti_spoof(images_np)

    if not is_live:
        return {
            "success": False,
            "status": "spoof_detected",
            "message": liveness_msg
        }

    # Face Recognition on primary frame
    primary_img = images_np[0]
    detected, all_ids, num_faces = predict_attendance(primary_img)

    if num_faces == 0:
        return {"success": False, "status": "no_face", "message": "No face detected in camera viewfinder."}
    if num_faces > 1:
        return {"success": False, "status": "multiple_faces", "message": "Multiple faces detected. Please scan one person at a time."}

    if detected:
        student_id = list(detected.keys())[0]
        all_students = get_all_students() or []
        student = next((s for s in all_students if s['student_id'] == student_id), None)
        if student:
            student_safe = {
                "student_id": student["student_id"],
                "name": student["name"],
                "has_voice": bool(student.get("voice_embedding"))
            }
            return {"success": True, "status": "recognized", "student": student_safe}

    return {"success": False, "status": "unrecognized", "message": "Face not recognized. Please register below."}


@app.post("/api/student/voice-login")
async def student_voice_login(payload: dict):
    audio_b64 = payload.get("audio")
    if not audio_b64:
        raise HTTPException(status_code=400, detail="Audio recording is required.")

    try:
        audio_bytes = decode_base64_audio(audio_b64)

        from src.pipelines.voice_pipeline import load_audio_array, check_voice_liveness_and_anti_replay, identify_speaker
        audio_arr, sr = load_audio_array(audio_bytes)
        is_live_voice, liveness_msg = check_voice_liveness_and_anti_replay(audio_arr, sr)

        if not is_live_voice:
            return {"success": False, "status": "spoof_detected", "message": liveness_msg}

        new_emb = get_voice_embedding(audio_bytes)
        if not new_emb:
            return {"success": False, "message": "Could not extract voice features. Please speak clearly."}

        all_students = get_all_students() or []
        target_query = (payload.get("target_student") or "").strip().lower()
        target_explicit = bool(payload.get("target_explicit"))

        # If user specified or spoke target student name/ID
        if target_query:
            target_matches = []
            for s in all_students:
                s_name = s["name"].lower()
                s_id = str(s["student_id"])
                name_tokens = [w for w in s_name.split() if len(w) >= 3]

                # Match if exact ID or whole word name appears in target_query
                is_id_match = (s_id == target_query)
                is_name_match = (s_name == target_query) or any(
                    re.search(r'\b' + re.escape(token) + r'\b', target_query) for token in name_tokens
                )

                if is_id_match or is_name_match:
                    target_matches.append(s)

            if target_matches:
                target_dict = {s["student_id"]: s["voice_embedding"] for s in target_matches}
                matched_id, score = identify_speaker(new_emb, target_dict, threshold=0.75)
                print(f"VoiceID Spoken-Name Scan: Matched {[s['name'] for s in target_matches]} -> ID {matched_id}, score: {score:.3f}")

                if matched_id:
                    matched_student = next((s for s in target_matches if s["student_id"] == matched_id), target_matches[0])
                    student_safe = {
                        "student_id": matched_student["student_id"],
                        "name": matched_student["name"],
                        "has_voice": True
                    }
                    return {
                        "success": True,
                        "status": "recognized",
                        "student": student_safe,
                        "score": round(score * 100, 1),
                        "message": f"Voice verified for {matched_student['name']} ({round(score * 100, 1)}% match)!"
                    }
                else:
                    return {
                        "success": False,
                        "status": "mismatch",
                        "message": f"Voiceprint does not match registered profile for {target_matches[0]['name']} ({round(score * 100, 1)}% match)."
                    }

            if target_explicit:
                return {
                    "success": False,
                    "status": "mismatch",
                    "message": "The requested student could not be verified by voice."
                }

        # 1:N Automatic Matching across all candidates
        candidates_dict = {
            s["student_id"]: s["voice_embedding"]
            for s in all_students if s.get("voice_embedding")
        }

        if not candidates_dict:
            return {"success": False, "message": "No students have registered voice biometric profiles yet."}

        matched_id, score = identify_speaker(new_emb, candidates_dict, threshold=0.65, min_margin=0.05)
        print(f"VoiceID 1:N Scan: Best match student {matched_id} with score {score:.3f} against {len(candidates_dict)} profiles")

        if matched_id:
            student = next((s for s in all_students if s["student_id"] == matched_id), None)
            if student:
                student_safe = {
                    "student_id": student["student_id"],
                    "name": student["name"],
                    "has_voice": True
                }
                return {
                    "success": True,
                    "status": "recognized",
                    "student": student_safe,
                    "score": round(score * 100, 1),
                    "message": f"Voice verified with {round(score * 100, 1)}% confidence!"
                }

        return {"success": False, "status": "unrecognized", "message": f"Voice profile not recognized (score: {round(score * 100, 1)}%). Speak closer to your mic or login with FaceID."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _store_voice_profile_later(student_id: int, audio_b64: str):
    try:
        audio_bytes = decode_base64_audio(audio_b64)
        voice_emb, voice_msg = safe_get_voice_embedding(audio_bytes)
        if voice_emb is None:
            print(f"Voice enrollment skipped for student {student_id}: {voice_msg}")
            return
        update_student_voice_embedding(student_id, voice_emb)
        print(f"Voice profile stored for student {student_id}")
    except Exception as e:
        print(f"Voice profile background update failed for student {student_id}: {e}")


@app.post("/api/student/register")
async def student_register_endpoint(payload: dict):
    name = payload.get("name")
    image_b64 = payload.get("image")
    audio_b64 = payload.get("audio")

    if not isinstance(name, str) or not name.strip() or not image_b64:
        raise HTTPException(status_code=400, detail="Name and camera face capture are required.")

    try:
        img_np = decode_base64_image(image_b64)
        encodings = get_face_embeddings(img_np)
    except Exception as e:
        print(f"Face enrollment error: {e}")
        raise HTTPException(status_code=400, detail="Could not process the face photo. Please retake it.")

    if not encodings:
        raise HTTPException(status_code=400, detail="Could not detect facial landmarks. Please retake photo.")

    face_emb = encodings[0].tolist()

    try:
        response_data = create_student(name.strip(), face_embedding=face_emb, voice_embedding=None)
        if response_data:
            student = response_data[0]
            if audio_b64:
                asyncio.create_task(_store_voice_profile_later(student["student_id"], audio_b64))

            student_safe = {
                "student_id": student["student_id"],
                "name": student["name"],
                "has_voice": False
            }
            return {"success": True, "student": student_safe, "message": f"Welcome, {name}!"}
        raise HTTPException(status_code=500, detail="Failed to create student profile.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------- Student Dashboard Endpoints ---------------------- #
@app.get("/api/student/{student_id}/courses")
async def student_courses(student_id: int):
    subjects = get_student_subjects(student_id) or []
    logs = get_student_attendance(student_id) or []

    stats_map = {}
    for log in logs:
        sid = log.get("subject_id")
        if sid not in stats_map:
            stats_map[sid] = {"total": 0, "attended": 0}
        stats_map[sid]["total"] += 1
        if log.get("is_present"):
            stats_map[sid]["attended"] += 1

    formatted = []
    for node in subjects:
        sub = node.get("subjects")
        if sub:
            sid = sub["subject_id"]
            stat = stats_map.get(sid, {"total": 0, "attended": 0})
            rate = round((stat["attended"] / stat["total"] * 100), 1) if stat["total"] > 0 else 0
            formatted.append({
                "subject_id": sid,
                "name": sub["name"],
                "subject_code": sub["subject_code"],
                "section": sub["section"],
                "total_sessions": stat["total"],
                "attended_sessions": stat["attended"],
                "attendance_rate": rate
            })

    return {"courses": formatted, "total_logs": len(logs)}


@app.post("/api/student/enroll")
async def student_enroll(req: EnrollRequest):
    code_clean = req.subject_code.strip().upper()
    res = supabase.table('subjects').select('subject_id, name, subject_code').eq('subject_code', code_clean).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Subject code not found.")

    subject = res.data[0]
    check = supabase.table('subject_students').select('*').eq('subject_id', subject['subject_id']).eq('student_id', req.student_id).execute()
    if check.data:
        raise HTTPException(status_code=400, detail=f"Already enrolled in {subject['name']}.")

    enroll_student_to_subject(req.student_id, subject['subject_id'])
    return {"success": True, "message": f"Successfully enrolled in {subject['name']}!"}


@app.post("/api/student/unenroll")
async def student_unenroll(req: UnenrollRequest):
    unenroll_student_to_subject(req.student_id, req.subject_id)
    return {"success": True, "message": "Unenrolled successfully."}


# ---------------------- Teacher Subject & Analytics Endpoints ---------------------- #
@app.get("/api/teacher/{teacher_id}/subjects")
async def teacher_subjects_endpoint(teacher_id: int):
    subjects = get_teacher_subjects(teacher_id) or []
    return {"subjects": subjects}


@app.post("/api/teacher/subjects")
async def create_subject_endpoint(req: CreateSubjectRequest):
    if not req.subject_code or not req.name or not req.section:
        raise HTTPException(status_code=400, detail="All subject fields are required.")
    
    created = create_subject(
        req.subject_code.strip().upper(),
        req.name.strip(),
        req.section.strip().upper(),
        req.teacher_id
    )
    return {"success": True, "subject": created}


@app.get("/api/teacher/{teacher_id}/attendance")
async def teacher_attendance_analytics(teacher_id: int):
    records = get_attendance_for_teacher(teacher_id) or []
    data = []
    for r in records:
        ts = r.get('timestamp')
        data.append({
            "ts_group": ts.split(".")[0] if ts else "N/A",
            "time": datetime.fromisoformat(ts).strftime("%Y-%m-%d %I:%M %p") if ts else "N/A",
            "subject": r['subjects']['name'],
            "subject_code": r['subjects']['subject_code'],
            "is_present": bool(r.get('is_present', False))
        })

    if not data:
        return {"summary": [], "metrics": {"total_sessions": 0, "total_students_checked": 0, "average_attendance": 0}}

    df = pd.DataFrame(data)
    summary_df = (
        df.groupby(['ts_group', 'time', 'subject', 'subject_code'])
        .agg(
            present_count=('is_present', 'sum'),
            total_count=('is_present', 'count')
        ).reset_index()
    )
    summary_df['rate'] = ((summary_df['present_count'] / summary_df['total_count']) * 100).round(1)

    total_sessions = len(summary_df)
    total_present = int(summary_df['present_count'].sum())
    total_count = int(summary_df['total_count'].sum())
    avg_rate = round((total_present / total_count * 100), 1) if total_count > 0 else 0

    return {
        "summary": summary_df.sort_values(by="ts_group", ascending=False).to_dict(orient="records"),
        "metrics": {
            "total_sessions": total_sessions,
            "total_students_checked": total_count,
            "total_present": total_present,
            "average_attendance": avg_rate
        }
    }


@app.get("/api/teacher/{teacher_id}/attendance/export")
async def export_attendance_csv(teacher_id: int):
    records = get_attendance_for_teacher(teacher_id) or []
    data = []
    for r in records:
        ts = r.get('timestamp')
        data.append({
            "Timestamp": datetime.fromisoformat(ts).strftime("%Y-%m-%d %I:%M %p") if ts else "N/A",
            "Course Name": r['subjects']['name'],
            "Course Code": r['subjects']['subject_code'],
            "Section": r['subjects']['section'],
            "Student ID": r.get('student_id'),
            "Is Present": "Yes" if r.get('is_present') else "No"
        })

    df = pd.DataFrame(data)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    
    return Response(
        content=stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_report_teacher_{teacher_id}.csv"}
    )


@app.get("/api/teacher/{teacher_id}/attendance/at-risk")
async def get_at_risk_students(teacher_id: int):
    """
    Identifies enrolled students across all courses whose attendance rate is below 75% (Defaulters) or between 75-80% (Warning).
    """
    subjects = get_teacher_subjects(teacher_id) or []
    at_risk = []

    for sub in subjects:
        sub_id = sub['subject_id']
        sub_code = sub['subject_code']
        sub_name = sub['name']
        sec = sub['section']

        # Enrolled students
        enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', sub_id).execute()
        enrolled = enrolled_res.data or []

        # Attendance logs for this subject
        logs_res = supabase.table('attendance_logs').select("*").eq('subject_id', sub_id).execute()
        logs = logs_res.data or []

        if not logs or not enrolled:
            continue

        # Count total distinct sessions
        sessions = set(log.get('timestamp', '').split('.')[0] for log in logs if log.get('timestamp'))
        total_sessions = len(sessions)
        if total_sessions == 0:
            continue

        for item in enrolled:
            student = item.get('students')
            if not student:
                continue
            sid = student['student_id']
            sname = student['name']

            attended_count = sum(
                1 for log in logs 
                if log.get('student_id') == sid and log.get('is_present')
            )
            rate = round((attended_count / total_sessions) * 100, 1)

            if rate < 75.0:
                status_label = "Defaulter (<75%)"
                severity = "danger"
            elif rate < 80.0:
                status_label = "Warning (75-80%)"
                severity = "warning"
            else:
                continue

            at_risk.append({
                "student_id": sid,
                "name": sname,
                "subject_id": sub_id,
                "subject_name": sub_name,
                "subject_code": sub_code,
                "section": sec,
                "attended": attended_count,
                "total": total_sessions,
                "rate": rate,
                "status": status_label,
                "severity": severity
            })

    # Sort lowest attendance first
    at_risk.sort(key=lambda x: x['rate'])
    return {"at_risk_students": at_risk, "total_defaulters": len([s for s in at_risk if s['severity'] == 'danger'])}


# ---------------------- Multimodal Attendance Recognition ---------------------- #
@app.post("/api/attendance/face-scan")
async def face_scan_attendance(payload: dict):
    subject_id = payload.get("subject_id")
    images_b64 = payload.get("images", [])

    if not subject_id or not images_b64:
        raise HTTPException(status_code=400, detail="Subject ID and at least one image are required.")

    # Fetch enrolled students
    enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', subject_id).execute()
    enrolled = enrolled_res.data or []

    if not enrolled:
        return {"results": [], "logs": [], "message": "No students enrolled in this course."}

    all_detected_ids = {}
    for idx, img_b64 in enumerate(images_b64):
        img_np = decode_base64_image(img_b64)
        detected, _, _ = predict_attendance(img_np)
        for sid in detected.keys():
            all_detected_ids.setdefault(int(sid), []).append(f"Photo {idx+1}")

    results = []
    attendance_to_log = []
    current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for node in enrolled:
        student = node['students']
        sid = int(student['student_id'])
        sources = all_detected_ids.get(sid, [])
        is_present = len(sources) > 0

        results.append({
            "name": student['name'],
            "student_id": sid,
            "source": ", ".join(sources) if is_present else "-",
            "is_present": is_present
        })

        attendance_to_log.append({
            "student_id": sid,
            "subject_id": subject_id,
            "timestamp": current_timestamp,
            "is_present": is_present
        })

    return {"results": results, "logs": attendance_to_log}


@app.post("/api/attendance/voice-scan")
async def voice_scan_attendance(payload: dict):
    subject_id = payload.get("subject_id")
    audio_b64 = payload.get("audio")

    if not subject_id or not audio_b64:
        raise HTTPException(status_code=400, detail="Course selection and classroom audio recording are required.")

    subject_id = int(subject_id)
    enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', subject_id).execute()
    enrolled = enrolled_res.data or []

    if not enrolled:
        return {"results": [], "logs": [], "message": "No students are currently enrolled in this course."}

    candidates_dict = {
        s['students']['student_id']: s['students']['voice_embedding']
        for s in enrolled if s['students'] and s['students'].get('voice_embedding')
    }

    results = []
    attendance_to_log = []
    current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    if not candidates_dict:
        # None of the students have voice embeddings yet
        for node in enrolled:
            student = node['students']
            sid = int(student['student_id'])
            results.append({
                "name": student['name'],
                "student_id": sid,
                "source": "⚠️ No Voice Profile Registered",
                "is_present": False
            })
            attendance_to_log.append({
                "student_id": sid,
                "subject_id": subject_id,
                "timestamp": current_timestamp,
                "is_present": False
            })
        return {
            "results": results,
            "logs": attendance_to_log,
            "message": "Notice: None of the enrolled students have voice biometric profiles registered yet."
        }

    try:
        audio_bytes = decode_base64_audio(audio_b64)
        detected_scores = process_bulk_audio(audio_bytes, candidates_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio processing error: {str(e)}")

    for node in enrolled:
        student = node['students']
        sid = int(student['student_id'])
        has_voice_profile = bool(student.get('voice_embedding'))
        score = detected_scores.get(sid, 0.0)
        is_present = bool(score > 0)

        if not has_voice_profile:
            source_desc = "⚠️ No Voice Profile Registered"
        elif is_present:
            source_desc = f"Acoustic Score: {round(score * 100, 1)}%"
        else:
            source_desc = "Not Heard"

        results.append({
            "name": student['name'],
            "student_id": sid,
            "source": source_desc,
            "is_present": is_present
        })

        attendance_to_log.append({
            "student_id": sid,
            "subject_id": subject_id,
            "timestamp": current_timestamp,
            "is_present": is_present
        })

    return {"results": results, "logs": attendance_to_log}


@app.post("/api/attendance/commit")
async def commit_attendance(req: AttendanceCommitRequest):
    if not req.logs:
        raise HTTPException(status_code=400, detail="No attendance logs to save.")
    
    try:
        res = create_attendance(req.logs)
        return {"success": True, "message": "Attendance successfully saved to database!", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------- QR Code Generation Endpoint ---------------------- #
@app.get("/api/subjects/qr/{subject_code}")
async def get_subject_qr(subject_code: str, host: Optional[str] = None):
    domain = host or os.environ.get("APP_DOMAIN", "localhost:8000")
    join_url = f"http://{domain}/?join-code={subject_code.upper()}" if not domain.startswith("http") else f"{domain}/?join-code={subject_code.upper()}"
    
    qr = segno.make(join_url)
    out = io.BytesIO()
    qr.save(out, kind='png', scale=8, border=2)
    out.seek(0)
    
    return StreamingResponse(out, media_type="image/png")


# ---------------------- Server Entry Point ---------------------- #
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
