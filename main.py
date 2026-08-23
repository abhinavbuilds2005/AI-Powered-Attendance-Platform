import os
import io
import base64
from datetime import datetime
from typing import List, Optional
import numpy as np
import pandas as pd
from PIL import Image
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
from src.pipelines.voice_pipeline import get_voice_embedding, process_bulk_audio

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
    image_b64 = payload.get("image")
    if not image_b64:
        raise HTTPException(status_code=400, detail="Image frame is required.")

    img_np = decode_base64_image(image_b64)
    detected, all_ids, num_faces = predict_attendance(img_np)

    if num_faces == 0:
        return {"success": False, "status": "no_face", "message": "No face detected in camera viewfinder."}
    if num_faces > 1:
        return {"success": False, "status": "multiple_faces", "message": "Multiple faces detected. Please scan one person at a time."}

    if detected:
        student_id = list(detected.keys())[0]
        all_students = get_all_students() or []
        student = next((s for s in all_students if s['student_id'] == student_id), None)
        if student:
            # Clean safe response
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
        new_emb = get_voice_embedding(audio_bytes)
        if not new_emb:
            return {"success": False, "message": "Could not extract voice features. Please speak clearly."}

        all_students = get_all_students() or []
        candidates_dict = {
            s["student_id"]: s["voice_embedding"]
            for s in all_students if s.get("voice_embedding")
        }

        if not candidates_dict:
            return {"success": False, "message": "No students have registered voice biometric profiles yet."}

        from src.pipelines.voice_pipeline import identify_speaker
        matched_id, score = identify_speaker(new_emb, candidates_dict, threshold=0.65)

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
                    "message": f"Voice matched with {round(score * 100, 1)}% confidence!"
                }

        return {"success": False, "status": "unrecognized", "message": "Voice profile not recognized. Try again or login using FaceID."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/student/register")
async def student_register_endpoint(payload: dict):
    name = payload.get("name")
    image_b64 = payload.get("image")
    audio_b64 = payload.get("audio")

    if not name or not image_b64:
        raise HTTPException(status_code=400, detail="Name and camera face capture are required.")

    img_np = decode_base64_image(image_b64)
    encodings = get_face_embeddings(img_np)

    if not encodings:
        raise HTTPException(status_code=400, detail="Could not detect facial landmarks. Please retake photo.")

    face_emb = encodings[0].tolist()
    voice_emb = None

    if audio_b64:
        try:
            audio_bytes = decode_base64_audio(audio_b64)
            voice_emb = get_voice_embedding(audio_bytes)
        except Exception as e:
            print(f"Voice enrollment notice: {e}")

    try:
        response_data = create_student(name.strip(), face_embedding=face_emb, voice_embedding=voice_emb)
        if response_data:
            train_classifier()
            student = response_data[0]
            student_safe = {
                "student_id": student["student_id"],
                "name": student["name"],
                "has_voice": bool(voice_emb)
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
    
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=attendance_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return response


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
