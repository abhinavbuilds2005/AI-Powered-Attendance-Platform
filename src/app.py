import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import threading
from src.routes.student import router as student_router
from src.routes.teacher import router as teacher_router
from src.routes.attendance import router as attendance_router
from src.routes.common import router as common_router

app = FastAPI(
    title="PresentAI API",
    description="Professional full-stack backend API for AI Attendance System supporting Face and Voice Biometric Recognition",
    version="2.0.0"
)

def _warmup_biometric_models():
    """Background worker to warm up Dlib face models, Resemblyzer voice encoder, and classifier."""
    try:
        from src.services.face_service import load_dlib_models, get_trained_model
        load_dlib_models()
        get_trained_model()
        print("[Warmup] Dlib face models and classifier initialized.")
    except Exception as e:
        print("[Warmup] Notice initializing face models:", e)

    try:
        from src.services.voice_service import load_voice_encoder
        load_voice_encoder()
        print("[Warmup] Resemblyzer voice encoder initialized.")
    except Exception as e:
        print("[Warmup] Notice initializing voice encoder:", e)

@app.on_event("startup")
def startup_event():
    # Pre-warm heavy models in a daemon thread so server starts accepting requests instantly
    threading.Thread(target=_warmup_biometric_models, daemon=True).start()

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
app.include_router(attendance_router, prefix="/api")

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
