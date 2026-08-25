from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routes.student import router as student_router
from src.routes.teacher import router as teacher_router
from src.routes.common import router as common_router

app = FastAPI(
    title="AI Attendance API",
    description="Professional refactored backend API for AI Attendance System supporting Face and Voice Recognition",
    version="2.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes with appropriate prefixes
app.include_router(common_router, prefix="/api")
app.include_router(student_router, prefix="/api")
app.include_router(teacher_router, prefix="/api")
