import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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

# Static files & Frontend serving
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
@app.head("/")
async def root():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "PresentAI API is live", "docs": "/docs", "health": "/api/health"}


@app.get("/health")
@app.head("/health")
async def health_root():
    return {"status": "healthy"}

