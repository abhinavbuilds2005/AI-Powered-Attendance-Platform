from fastapi import APIRouter
from datetime import datetime

router = APIRouter(tags=["Common"])

@router.get("/health")
async def health_check():
    """Service health and heartbeat check."""
    return {
        "status": "healthy",
        "time": datetime.utcnow().isoformat()
    }
