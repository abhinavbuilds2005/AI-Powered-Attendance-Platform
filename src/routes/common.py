from fastapi import APIRouter, HTTPException, Response
from datetime import datetime
from typing import Optional
import segno
import io

from src.schemas.schemas import TeacherRegisterRequest, TeacherLoginRequest
from src.services.db_service import check_teacher_exists, create_teacher, teacher_login

router = APIRouter(tags=["Common"])


@router.get("/health")
async def health_check():
    """Service health and heartbeat check."""
    return {
        "status": "healthy",
        "time": datetime.utcnow().isoformat()
    }


@router.get("/subjects/qr/{code}")
async def get_subject_qr_code(code: str, host: Optional[str] = None):
    """Generate dynamic QR Code image for course enrollment."""
    try:
        host_url = f"http://{host}" if host and not host.startswith("http") else (host or "http://localhost:8000")
        join_url = f"{host_url}/?join-code={code}"
        qr = segno.make(join_url)
        out = io.BytesIO()
        qr.save(out, kind='png', scale=8, border=2)
        return Response(content=out.getvalue(), media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QR generation failed: {str(e)}")


@router.post("/auth/teacher/login")
async def auth_teacher_login(req: TeacherLoginRequest):
    """Auth alias for teacher login."""
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


@router.post("/auth/teacher/register")
async def auth_teacher_register(req: TeacherRegisterRequest):
    """Auth alias for teacher register."""
    try:
        username = req.username.strip()
        if not username or not req.password:
            raise HTTPException(status_code=400, detail="Username and password are required.")
        if check_teacher_exists(username):
            raise HTTPException(status_code=400, detail="Username is already taken.")
        res = create_teacher(username, req.password, req.name.strip())
        if res:
            return {"success": True, "message": "Account created successfully. You can now log in."}
        raise HTTPException(status_code=500, detail="Database insertion failed.")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
