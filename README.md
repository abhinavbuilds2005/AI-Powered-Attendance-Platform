# PresentAI 🎓📸🎙️

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

PresentAI is a production-ready, full-stack AI attendance platform built with **FastAPI**, **Vanilla HTML5/CSS/JavaScript**, and **Supabase**. It leverages native browser WebCam and microphone APIs for low-latency facial recognition (**dlib + SVM**) and voice speaker identification (**Resemblyzer + Librosa**).

---

## 🌟 Key Features

- **📸 Native Browser WebCam FaceID**:
  - Live `<video>` stream scanning with circular target alignment.
  - Multi-photo classroom face scanning to mark multiple students present at once.
  - 128-dimensional facial descriptors with Euclidean distance verification.
- **🎙️ Acoustic Voice Biometrics**:
  - Native browser `MediaRecorder` audio capture.
  - Silence segmentation and speaker utterance matching against enrolled student voice prints.
- **👨‍🏫 Teacher Studio**:
  - **Take Attendance**: Upload classroom group snapshots or take live webcam captures; run AI face analysis or audio analysis.
  - **Verification Modal**: Review present/absent student breakdown with match sources before persisting to database.
  - **Manage Courses & QR Sharing**: Generate dynamic QR codes and direct enrollment links (`/?join-code=CS101`).
  - **Attendance Analytics & CSV Export**: Real-time aggregated timelines and 1-click **Export to CSV**.
- **👤 Student Biometric Portal**:
  - Passwordless FaceID login.
  - Instant new student profile onboarding with optional voice sample registration.
  - Personal dashboard tracking attendance rates per enrolled course.

---

## 🚀 Running Locally

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Create a `.env` file in the project root:
```env
SUPABASE_URL=https://hctrotwtwdqqencyfwae.supabase.co
SUPABASE_KEY=your-supabase-key
PORT=8000
```

### 3. Start the FastAPI Server
```bash
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## ☁️ Deploying on Render (Web Service)

### Method A: Deploy via Blueprint (`render.yaml`)
1. Push this repository to GitHub or GitLab.
2. In the [Render Dashboard](https://dashboard.render.com/), click **New +** > **Blueprint**.
3. Connect your repository. Render will automatically detect `render.yaml`.
4. Set your `SUPABASE_URL` and `SUPABASE_KEY` environment variables.

### Method B: Manual Web Service Setup
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**:
  - `SUPABASE_URL` = `https://your-project.supabase.co`
  - `SUPABASE_KEY` = `your-supabase-key`
  - `PYTHON_VERSION` = `3.10.12`

---

## 🗄️ Supabase SQL Database Schema

Run this script in your **Supabase SQL Editor**:

```sql
CREATE TABLE IF NOT EXISTS teachers (
    teacher_id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS students (
    student_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    face_embedding JSONB,
    voice_embedding JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subjects (
    subject_id SERIAL PRIMARY KEY,
    subject_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    section TEXT NOT NULL,
    teacher_id INT REFERENCES teachers(teacher_id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subject_students (
    id SERIAL PRIMARY KEY,
    student_id INT REFERENCES students(student_id) ON DELETE CASCADE,
    subject_id INT REFERENCES subjects(subject_id) ON DELETE CASCADE,
    enrolled_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(student_id, subject_id)
);

CREATE TABLE IF NOT EXISTS attendance_logs (
    id SERIAL PRIMARY KEY,
    student_id INT REFERENCES students(student_id) ON DELETE CASCADE,
    subject_id INT REFERENCES subjects(subject_id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    is_present BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```