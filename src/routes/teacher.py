import io
import csv
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import List, Optional

from src.schemas.schemas import TeacherRegisterRequest, TeacherLoginRequest, CreateSubjectRequest
from src.services.db_service import (
    check_teacher_exists, create_teacher, teacher_login,
    get_teacher_subjects, create_subject, supabase
)

router = APIRouter(prefix="/teacher", tags=["Teacher"])


@router.post("/register")
async def teacher_register_api(req: TeacherRegisterRequest):
    """Register a new teacher."""
    try:
        username = req.username.strip()
        if not username or not req.password:
            raise HTTPException(status_code=400, detail="Username and password are required.")
        if check_teacher_exists(username):
            raise HTTPException(status_code=400, detail="Username is already taken. Please choose another.")
        res = create_teacher(username, req.password, req.name.strip())
        if res:
            return {"success": True, "message": "Account created successfully. You can now log in."}
        raise HTTPException(status_code=500, detail="Database insertion failed.")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login")
async def teacher_login_api(req: TeacherLoginRequest):
    """Authenticate teacher credentials."""
    try:
        teacher = teacher_login(req.username.strip(), req.password)
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
    """Retrieve all subjects taught by a teacher."""
    try:
        subs = get_teacher_subjects(teacher_id)
        return {"subjects": subs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subjects")
@router.post("/subjects/create")
async def teacher_create_subject_api(req: CreateSubjectRequest):
    """Create a new course subject for a teacher."""
    try:
        code = req.subject_code.strip()
        name = req.name.strip()
        section = req.section.strip()
        if not code or not name or not section:
            raise HTTPException(status_code=400, detail="Course code, name, and section are all required.")

        res = create_subject(code, name, section, req.teacher_id)
        subject = res[0] if res else {}
        return {"success": True, "subject": subject, "message": "Course created successfully!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{teacher_id}/attendance")
async def teacher_attendance_analytics_api(teacher_id: int):
    """Retrieve analytics and summary breakdown for teacher's conducted attendance sessions."""
    try:
        subjects = get_teacher_subjects(teacher_id)
        subject_ids = [s['subject_id'] for s in subjects]

        if not subject_ids:
            return {
                "metrics": {
                    "total_sessions": 0,
                    "total_present": 0,
                    "total_students_checked": 0,
                    "average_attendance": 0
                },
                "summary": []
            }

        logs_res = supabase.table('attendance_logs').select('*, subjects(*)').in_('subject_id', subject_ids).execute()
        logs = logs_res.data or []

        sessions_dict = {}
        for log in logs:
            key = (log['timestamp'], log['subject_id'])
            if key not in sessions_dict:
                sessions_dict[key] = {
                    "time": log['timestamp'],
                    "subject": log.get('subjects', {}).get('name', 'Course'),
                    "subject_code": log.get('subjects', {}).get('subject_code', ''),
                    "present_count": 0,
                    "total_count": 0
                }
            sessions_dict[key]["total_count"] += 1
            if log.get('is_present'):
                sessions_dict[key]["present_count"] += 1

        summary = []
        total_present = 0
        total_checked = 0
        for s in sessions_dict.values():
            s["rate"] = round((s["present_count"] / s["total_count"]) * 100) if s["total_count"] > 0 else 0
            total_present += s["present_count"]
            total_checked += s["total_count"]
            summary.append(s)

        summary.sort(key=lambda x: x["time"], reverse=True)
        total_sessions = len(sessions_dict)
        avg_rate = round((total_present / total_checked) * 100) if total_checked > 0 else 0

        metrics = {
            "total_sessions": total_sessions,
            "total_present": total_present,
            "total_students_checked": total_checked,
            "average_attendance": avg_rate
        }
        return {"metrics": metrics, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{teacher_id}/attendance/at-risk")
async def teacher_at_risk_students_api(teacher_id: int):
    """Calculate at-risk students below the mandatory 75% attendance threshold."""
    try:
        subjects = get_teacher_subjects(teacher_id)
        at_risk_list = []

        for sub in subjects:
            subject_id = sub['subject_id']
            enr_res = supabase.table('subject_students').select('*, students(*)').eq('subject_id', subject_id).execute()
            enrolled = enr_res.data or []

            logs_res = supabase.table('attendance_logs').select('*').eq('subject_id', subject_id).execute()
            logs = logs_res.data or []

            timestamps = set(l['timestamp'] for l in logs)
            total_sessions = len(timestamps)

            if total_sessions == 0:
                continue

            for node in enrolled:
                student = node.get('students')
                if not student:
                    continue
                sid = student['student_id']
                attended = len([l for l in logs if l.get('student_id') == sid and l.get('is_present')])
                rate = round((attended / total_sessions) * 100)

                if rate < 75:
                    at_risk_list.append({
                        "name": student['name'],
                        "student_id": sid,
                        "subject_name": sub['name'],
                        "subject_code": sub['subject_code'],
                        "attended": attended,
                        "total": total_sessions,
                        "rate": rate,
                        "status": "🔴 Critical (<75%)",
                        "severity": "danger"
                    })
                elif rate < 80:
                    at_risk_list.append({
                        "name": student['name'],
                        "student_id": sid,
                        "subject_name": sub['name'],
                        "subject_code": sub['subject_code'],
                        "attended": attended,
                        "total": total_sessions,
                        "rate": rate,
                        "status": "🟡 Warning (75-80%)",
                        "severity": "warning"
                    })

        return {"at_risk_students": at_risk_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{teacher_id}/attendance/export")
async def export_teacher_attendance_csv(teacher_id: int):
    """Download attendance records for teacher's courses as CSV."""
    try:
        subjects = get_teacher_subjects(teacher_id)
        subject_ids = [s['subject_id'] for s in subjects]
        if not subject_ids:
            logs = []
        else:
            logs_res = supabase.table('attendance_logs').select('*, students(name), subjects(name, subject_code)').in_('subject_id', subject_ids).execute()
            logs = logs_res.data or []

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Timestamp", "Course Code", "Course Name", "Student ID", "Student Name", "Attendance Status"])

        for l in logs:
            writer.writerow([
                l.get('timestamp', ''),
                l.get('subjects', {}).get('subject_code', ''),
                l.get('subjects', {}).get('name', ''),
                l.get('student_id', ''),
                l.get('students', {}).get('name', ''),
                "Present" if l.get('is_present') else "Absent"
            ])

        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode('utf-8')),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=attendance_export_teacher_{teacher_id}.csv"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
