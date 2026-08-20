// ==================== APP CONFIGURATION & STATE ====================
// Adjust API URL base if your Render backend runs on a custom domain.
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
    ? 'http://127.0.0.1:8000/api' 
    : 'https://ai-powered-attendance-platform.onrender.com/api';

const state = {
    currentScreen: 'screen-home',
    student: null, // Logged in student
    teacher: null, // Logged in teacher
    activeTeacherTab: 'tab-take-attendance',
    
    // Webcam stream handles
    loginStream: null,
    regStream: null,
    studentRegSnapshotBlob: null,
    
    // Voice enrollment handles (student)
    mediaRecorder: null,
    audioChunks: [],
    isRecordingVoice: false,
    recordedAudioBlob: null,
    voiceTimerInterval: null,
    
    // Teacher attendance items
    teacherSubjects: [],
    selectedClassroomPhotos: [], // Array of File objects
    activeBiometricMode: 'face', // 'face' or 'voice'
    analyzedAttendanceResults: null, // Stores results before saving
    
    // Teacher voice check-in recording
    teacherVoiceRecorder: null,
    teacherAudioChunks: [],
    isTeacherRecording: false,
    teacherVoiceBlob: null,
    teacherTimerInterval: null
};

// ==================== INITIALIZATION & EVENT LISTENERS ====================
document.addEventListener('DOMContentLoaded', () => {
    initRouter();
    initHomePortal();
    initStudentAuth();
    initStudentDashboard();
    initTeacherAuth();
    initTeacherDashboard();
    initModals();
});

// ==================== TOAST NOTIFICATION HELPERS ====================
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let iconName = 'info';
    if (type === 'success') iconName = 'check_circle';
    if (type === 'error') iconName = 'error';
    if (type === 'warning') iconName = 'warning';
    
    toast.innerHTML = `
        <span class="material-symbols-rounded toast-icon">${iconName}</span>
        <span class="toast-message">${message}</span>
    `;
    
    container.appendChild(toast);
    
    // Slide out and remove toast after 3.5s
    setTimeout(() => {
        toast.style.animation = 'toastSlideIn 0.3s ease-out reverse';
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3200);
}

// ==================== ROUTING SYSTEM ====================
function initRouter() {
    navigateTo('screen-home');
}

function navigateTo(screenId) {
    // 1. Clean up active media streams before switching screens
    stopMediaStreams();

    // 2. Hide all screens, show target screen
    const screens = document.querySelectorAll('.screen');
    screens.forEach(s => s.classList.remove('active'));
    
    const target = document.getElementById(screenId);
    if (target) {
        target.classList.add('active');
        state.currentScreen = screenId;
    }

    // 3. Run screen-specific setup
    if (screenId === 'screen-student-login') {
        startWebcam('student-login-video', 'loginStream');
    } else if (screenId === 'screen-student-register') {
        resetStudentRegistrationForm();
        startWebcam('student-reg-video', 'regStream');
    } else if (screenId === 'screen-student-dashboard') {
        loadStudentDashboard();
    } else if (screenId === 'screen-teacher-dashboard') {
        loadTeacherDashboard();
    }
}

function stopMediaStreams() {
    // Student Login camera
    if (state.loginStream) {
        state.loginStream.getTracks().forEach(track => track.stop());
        state.loginStream = null;
    }
    // Student Reg camera
    if (state.regStream) {
        state.regStream.getTracks().forEach(track => track.stop());
        state.regStream = null;
    }
    // Audio recording interval cleanup
    if (state.voiceTimerInterval) {
        clearInterval(state.voiceTimerInterval);
        state.voiceTimerInterval = null;
    }
    if (state.teacherTimerInterval) {
        clearInterval(state.teacherTimerInterval);
        state.teacherTimerInterval = null;
    }
}

// ==================== SCREEN 1: HOME PORTAL ====================
function initHomePortal() {
    document.getElementById('btn-portal-student').addEventListener('click', () => {
        navigateTo('screen-student-login');
    });
    
    document.getElementById('btn-portal-teacher').addEventListener('click', () => {
        navigateTo('screen-teacher-login');
    });
}

// ==================== SCREEN 2 & 3: STUDENT AUTH (FACE ID & REG) ====================
function initStudentAuth() {
    // Login Screen Back Btn
    document.getElementById('btn-student-login-back').addEventListener('click', () => {
        navigateTo('screen-home');
    });

    // Face Recognition Capture Action
    document.getElementById('btn-student-login-capture').addEventListener('click', async () => {
        const video = document.getElementById('student-login-video');
        const canvas = document.getElementById('student-login-canvas');
        const statusDiv = document.getElementById('student-login-status');
        
        if (!video.srcObject) {
            showToast('Camera not available!', 'error');
            return;
        }

        // Draw photo onto canvas
        const context = canvas.getContext('2d');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        // Convert canvas image to Blob
        canvas.toBlob(async (blob) => {
            const formData = new FormData();
            formData.append('file', blob, 'selfie.jpg');

            statusDiv.innerHTML = '<span style="color:var(--color-primary)">AI Scanning facial features...</span>';
            showToast('Scanning face...', 'info');

            try {
                const response = await fetch(`${API_BASE}/student/login-face`, {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    if (data.success) {
                        state.student = data.student;
                        statusDiv.innerHTML = `<span style="color:var(--color-success)">Welcome back, ${data.student.name}!</span>`;
                        showToast(`Access granted! Welcome ${data.student.name}`, 'success');
                        setTimeout(() => {
                            navigateTo('screen-student-dashboard');
                            statusDiv.innerHTML = '';
                        }, 1200);
                    } else {
                        statusDiv.innerHTML = `<span style="color:var(--color-warning)">Face not recognized. Redirecting to Register...</span>`;
                        showToast('Face not recognized! Create a profile.', 'warning');
                        setTimeout(() => {
                            navigateTo('screen-student-register');
                            statusDiv.innerHTML = '';
                        }, 2000);
                    }
                } else {
                    statusDiv.innerHTML = `<span style="color:var(--color-danger)">Error: ${data.detail || 'Scan failed'}</span>`;
                    showToast(data.detail || 'Analysis error', 'error');
                }
            } catch (err) {
                console.error(err);
                statusDiv.innerHTML = '<span style="color:var(--color-danger)">Network/Server connection failure.</span>';
                showToast('Failed to connect to ML backend.', 'error');
            }
        }, 'image/jpeg');
    });

    // Registration Screen Back Btn
    document.getElementById('btn-student-register-back').addEventListener('click', () => {
        navigateTo('screen-student-login');
    });

    // Reg Snap Trigger
    document.getElementById('btn-student-reg-snap').addEventListener('click', () => {
        const video = document.getElementById('student-reg-video');
        const canvas = document.getElementById('student-reg-canvas');
        const img = document.getElementById('student-reg-img');
        const overlay = document.getElementById('snap-overlay');
        
        const context = canvas.getContext('2d');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        canvas.toBlob((blob) => {
            state.studentRegSnapshotBlob = blob;
            img.src = URL.createObjectURL(blob);
            
            // Toggle view visibility
            video.classList.add('hidden');
            img.classList.remove('hidden');
            overlay.textContent = 'Snapshot captured!';
            overlay.style.background = 'rgba(16, 185, 129, 0.4)';
            
            showToast('Face captured!', 'success');
        }, 'image/jpeg');
    });

    // Voice record button setup
    const btnVoiceRecord = document.getElementById('btn-voice-record');
    btnVoiceRecord.addEventListener('click', () => {
        if (!state.isRecordingVoice) {
            startVoiceRecording();
        } else {
            stopVoiceRecording();
        }
    });

    // Submit Student Profile registration
    document.getElementById('btn-student-register-submit').addEventListener('click', async () => {
        const nameInput = document.getElementById('reg-student-name');
        const name = nameInput.value.trim();
        
        if (!name) {
            showToast('Please enter your full name!', 'warning');
            return;
        }
        if (!state.studentRegSnapshotBlob) {
            showToast('Please take your photo snapshot!', 'warning');
            return;
        }

        const formData = new FormData();
        formData.append('name', name);
        formData.append('image', state.studentRegSnapshotBlob, 'profile.jpg');
        
        if (state.recordedAudioBlob) {
            formData.append('audio', state.recordedAudioBlob, 'voice.wav');
        }

        showToast('Saving profile & training AI model...', 'info');
        
        try {
            const response = await fetch(`${API_BASE}/student/register`, {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            
            if (response.ok && data.success) {
                state.student = data.student;
                showToast(`Profile created! Welcome ${data.student.name}`, 'success');
                navigateTo('screen-student-dashboard');
            } else {
                showToast(data.detail || 'Registration failed', 'error');
            }
        } catch (err) {
            console.error(err);
            showToast('Server connection failed.', 'error');
        }
    });
}

function resetStudentRegistrationForm() {
    document.getElementById('reg-student-name').value = '';
    state.studentRegSnapshotBlob = null;
    state.recordedAudioBlob = null;
    
    const video = document.getElementById('student-reg-video');
    const img = document.getElementById('student-reg-img');
    const overlay = document.getElementById('snap-overlay');
    
    video.classList.remove('hidden');
    img.classList.add('hidden');
    img.src = '';
    overlay.textContent = 'Ready for snapshot';
    overlay.style.background = 'rgba(0,0,0,0.6)';
    
    const wave = document.getElementById('waveform-container');
    const timer = document.getElementById('voice-timer');
    const recText = document.getElementById('voice-record-text');
    const micIcon = document.getElementById('mic-icon');
    
    wave.classList.add('hidden');
    timer.classList.add('hidden');
    timer.textContent = '00:00';
    recText.textContent = 'Record Voice';
    micIcon.textContent = 'mic';
    
    state.isRecordingVoice = false;
}

// Start device webcam streams
async function startWebcam(videoId, streamStateKey) {
    const video = document.getElementById(videoId);
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: 'user' }
        });
        video.srcObject = stream;
        state[streamStateKey] = stream;
    } catch (err) {
        console.error(err);
        showToast('Unable to access webcam. Please check permissions.', 'error');
    }
}

// Student Voice check recording functions
async function startVoiceRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        state.audioChunks = [];
        
        state.mediaRecorder = new MediaRecorder(stream);
        state.mediaRecorder.ondataavailable = (event) => {
            state.audioChunks.push(event.data);
        };
        
        state.mediaRecorder.onstop = () => {
            state.recordedAudioBlob = new Blob(state.audioChunks, { type: 'audio/wav' });
            showToast('Voice recorded successfully!', 'success');
            
            // Stop tracks
            stream.getTracks().forEach(track => track.stop());
        };
        
        state.mediaRecorder.start();
        state.isRecordingVoice = true;
        
        // UI updates
        document.getElementById('voice-record-text').textContent = 'Stop Recording';
        document.getElementById('mic-icon').textContent = 'stop';
        document.getElementById('waveform-container').classList.remove('hidden');
        
        const timer = document.getElementById('voice-timer');
        timer.classList.remove('hidden');
        
        let seconds = 0;
        state.voiceTimerInterval = setInterval(() => {
            seconds++;
            const m = String(Math.floor(seconds / 60)).padStart(2, '0');
            const s = String(seconds % 60).padStart(2, '0');
            timer.textContent = `${m}:${s}`;
        }, 1000);
        
    } catch (err) {
        console.error(err);
        showToast('Microphone access denied!', 'error');
    }
}

function stopVoiceRecording() {
    if (state.mediaRecorder && state.isRecordingVoice) {
        state.mediaRecorder.stop();
        state.isRecordingVoice = false;
        
        clearInterval(state.voiceTimerInterval);
        state.voiceTimerInterval = null;
        
        document.getElementById('voice-record-text').textContent = 'Re-record Voice';
        document.getElementById('mic-icon').textContent = 'mic';
        document.getElementById('waveform-container').classList.add('hidden');
    }
}

// ==================== SCREEN 4: STUDENT DASHBOARD ====================
function initStudentDashboard() {
    document.getElementById('btn-student-logout').addEventListener('click', () => {
        state.student = null;
        showToast('Logged out successfully', 'info');
        navigateTo('screen-home');
    });

    document.getElementById('btn-student-open-enroll').addEventListener('click', () => {
        openEnrollmentModal();
    });
}

async function loadStudentDashboard() {
    if (!state.student) return;
    
    document.getElementById('student-welcome-name').textContent = state.student.name;
    
    try {
        const response = await fetch(`${API_BASE}/student/${state.student.student_id}/dashboard`);
        if (!response.ok) throw new Error('Data fetch failed');
        
        const data = await response.json();
        const subjects = data.subjects;
        const logs = data.logs;
        
        // Calculate metrics
        const statsMap = {};
        logs.forEach(log => {
            const sid = log.subject_id;
            if (!statsMap[sid]) statsMap[sid] = { total: 0, attended: 0 };
            statsMap[sid].total++;
            if (log.is_present) statsMap[sid].attended++;
        });

        let totalSessions = 0;
        let totalAttended = 0;
        
        // Ingest courses grid
        const grid = document.getElementById('student-course-grid');
        grid.innerHTML = '';
        
        if (subjects.length === 0) {
            grid.innerHTML = `
                <div class="glass-panel" style="grid-column:1/-1; padding:40px; text-align:center; color:var(--text-secondary)">
                    <span class="material-symbols-rounded" style="font-size:3rem; margin-bottom:10px; color:var(--text-muted)">inbox</span>
                    <p>You haven't enrolled in any subjects yet. Click "Enroll in Subject" above to join courses.</p>
                </div>
            `;
        } else {
            subjects.forEach(node => {
                const sub = node.subjects;
                const stats = statsMap[sub.subject_id] || { total: 0, attended: 0 };
                
                totalSessions += stats.total;
                totalAttended += stats.attended;
                
                const percent = stats.total > 0 ? Math.round((stats.attended / stats.total) * 100) : 0;
                
                const card = document.createElement('div');
                card.className = 'course-card';
                card.innerHTML = `
                    <div class="course-info">
                        <h4>${sub.name}</h4>
                        <span class="course-code">📘 ${sub.subject_code} • Section ${sub.section}</span>
                    </div>
                    <div>
                        <div class="course-card-metrics">
                            <div>
                                <span class="card-metric-num">${stats.attended}</span>
                                <span class="card-metric-lbl">Attended</span>
                            </div>
                            <div>
                                <span class="card-metric-num">${stats.total}</span>
                                <span class="card-metric-lbl">Total Classes</span>
                            </div>
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span class="badge" style="background:rgba(139,92,246,0.1); color:var(--color-primary); font-weight:700">${percent}% Rate</span>
                            <button class="btn btn-danger-tertiary btn-icon btn-unenroll" data-id="${sub.subject_id}">
                                <span class="material-symbols-rounded">delete</span> Drop
                            </button>
                        </div>
                    </div>
                `;
                
                grid.appendChild(card);
            });
            
            // Set unenroll buttons click
            document.querySelectorAll('.btn-unenroll').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const subjectId = e.currentTarget.dataset.id;
                    if (confirm('Are you sure you want to unenroll from this course?')) {
                        await unenrollStudent(subjectId);
                    }
                });
            });
        }
        
        // Draw progress gauges
        document.getElementById('student-total-attended').textContent = totalAttended;
        document.getElementById('student-total-sessions').textContent = totalSessions;
        
        const overallPercent = totalSessions > 0 ? Math.round((totalAttended / totalSessions) * 100) : 0;
        document.getElementById('student-attendance-percent').textContent = `${overallPercent}%`;
        
        // SVG Ring animation calculation
        const circle = document.getElementById('student-progress-circle');
        const radius = circle.r.baseVal.value;
        const circumference = 2 * Math.PI * radius;
        circle.style.strokeDasharray = `${circumference} ${circumference}`;
        
        const offset = circumference - (overallPercent / 100) * circumference;
        circle.style.strokeDashoffset = offset;
        
    } catch (err) {
        console.error(err);
        showToast('Failed to load student dashboard details.', 'error');
    }
}

async function unenrollStudent(subjectId) {
    try {
        const response = await fetch(`${API_BASE}/student/unenroll`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                student_id: state.student.student_id,
                subject_id: parseInt(subjectId)
            })
        });
        const data = await response.json();
        if (response.ok && data.success) {
            showToast('Successfully unenrolled!', 'success');
            loadStudentDashboard();
        } else {
            showToast(data.detail || 'Failed to unenroll', 'error');
        }
    } catch (err) {
        console.error(err);
        showToast('Connection failed.', 'error');
    }
}

// ==================== SCREEN 5 & 6: TEACHER AUTH (LOGIN & REGISTER) ====================
function initTeacherAuth() {
    // Back navigation
    document.getElementById('btn-teacher-login-back').addEventListener('click', () => navigateTo('screen-home'));
    document.getElementById('btn-teacher-register-back').addEventListener('click', () => navigateTo('screen-teacher-login'));
    
    // Auth route links
    document.getElementById('link-go-to-teacher-register').addEventListener('click', () => navigateTo('screen-teacher-register'));
    document.getElementById('link-go-to-teacher-login').addEventListener('click', () => navigateTo('screen-teacher-login'));

    // Submit teacher Login Form
    const loginForm = document.getElementById('form-teacher-login');
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('login-teacher-username').value.trim();
        const password = document.getElementById('login-teacher-password').value;
        
        try {
            const response = await fetch(`${API_BASE}/teacher/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await response.json();
            
            if (response.ok && data.success) {
                state.teacher = data.teacher;
                showToast(`Welcome back, Prof. ${data.teacher.name}!`, 'success');
                navigateTo('screen-teacher-dashboard');
                loginForm.reset();
            } else {
                showToast(data.detail || 'Invalid username/password', 'error');
            }
        } catch (err) {
            console.error(err);
            showToast('Backend connection failed.', 'error');
        }
    });

    // Submit teacher Registration Form
    const registerForm = document.getElementById('form-teacher-register');
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('reg-teacher-name').value.trim();
        const username = document.getElementById('reg-teacher-username').value.trim();
        const password = document.getElementById('reg-teacher-password').value;
        const confirmPass = document.getElementById('reg-teacher-confirm-password').value;
        
        if (password.length < 6) {
            showToast('Password must be at least 6 characters!', 'warning');
            return;
        }
        if (password !== confirmPass) {
            showToast('Passwords do not match!', 'warning');
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/teacher/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, username, password })
            });
            const data = await response.json();
            
            if (response.ok && data.success) {
                showToast(data.detail || 'Account created successfully!', 'success');
                navigateTo('screen-teacher-login');
                registerForm.reset();
            } else {
                showToast(data.detail || 'Registration failed', 'error');
            }
        } catch (err) {
            console.error(err);
            showToast('Backend connection failed.', 'error');
        }
    });
}

// ==================== SCREEN 7: TEACHER DASHBOARD ====================
function initTeacherDashboard() {
    // Logout action
    document.getElementById('btn-teacher-logout').addEventListener('click', () => {
        state.teacher = null;
        showToast('Logged out successfully', 'info');
        navigateTo('screen-home');
    });

    // Sidebar navigation tabs
    const navItems = document.querySelectorAll('.sidebar-nav .nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            const tabId = e.currentTarget.dataset.tab;
            
            // Mark active nav
            navItems.forEach(btn => btn.classList.remove('active'));
            e.currentTarget.classList.add('active');
            
            // Trigger panes visibility
            const panes = document.querySelectorAll('.tab-pane');
            panes.forEach(p => p.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            
            state.activeTeacherTab = tabId;
            loadActiveTeacherTabContent();
        });
    });

    // Setup attendance biometric toggle
    const btnModeFace = document.getElementById('btn-mode-face');
    const btnModeVoice = document.getElementById('btn-mode-voice');
    const panelFace = document.getElementById('panel-attendance-face');
    const panelVoice = document.getElementById('panel-attendance-voice');

    btnModeFace.addEventListener('click', () => {
        btnModeFace.classList.add('active');
        btnModeVoice.classList.remove('active');
        panelFace.classList.remove('hidden');
        panelVoice.classList.add('hidden');
        state.activeBiometricMode = 'face';
    });

    btnModeVoice.addEventListener('click', () => {
        btnModeVoice.classList.add('active');
        btnModeFace.classList.remove('active');
        panelVoice.classList.remove('hidden');
        panelFace.classList.add('hidden');
        state.activeBiometricMode = 'voice';
    });

    // Uploader triggers for Face
    const browseBtn = document.getElementById('btn-browse-photos');
    const photoInput = document.getElementById('classroom-photo-input');
    const dropZone = document.getElementById('photo-drop-zone');

    browseBtn.addEventListener('click', () => photoInput.click());
    photoInput.addEventListener('change', (e) => handleClassroomPhotosSelect(e.target.files));

    // Drag and drop events
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleClassroomPhotosSelect(e.dataTransfer.files);
    });

    // Clear photos
    document.getElementById('btn-clear-photos').addEventListener('click', () => {
        state.selectedClassroomPhotos = [];
        renderPhotoThumbnails();
    });

    // Run deep face analysis
    document.getElementById('btn-run-face-analysis').addEventListener('click', async () => {
        const subjectSelect = document.getElementById('attendance-subject-select');
        const subjectId = subjectSelect.value;
        
        if (!subjectId) {
            showToast('Please select a subject first!', 'warning');
            return;
        }
        if (state.selectedClassroomPhotos.length === 0) {
            showToast('Please upload at least one classroom photo!', 'warning');
            return;
        }

        const formData = new FormData();
        formData.append('subject_id', subjectId);
        state.selectedClassroomPhotos.forEach((file) => {
            formData.append('files', file);
        });

        showToast('Running AI face analysis on classroom photos...', 'info');
        
        try {
            const response = await fetch(`${API_BASE}/teacher/take-attendance-face`, {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            
            if (response.ok && data.success) {
                state.analyzedAttendanceResults = data.results;
                renderAnalysisResults(data.results);
            } else {
                showToast(data.detail || 'Analysis failed', 'error');
            }
        } catch (err) {
            console.error(err);
            showToast('Server connection failed.', 'error');
        }
    });

    // Uploader triggers for Voice
    const browseAudioBtn = document.getElementById('btn-browse-audio');
    const audioInput = document.getElementById('classroom-audio-input');
    const voiceDropZone = document.getElementById('voice-drop-zone');

    browseAudioBtn.addEventListener('click', () => audioInput.click());
    audioInput.addEventListener('change', async (e) => {
        if (e.target.files.length > 0) {
            await runVoiceRollCallAnalysis(e.target.files[0]);
        }
    });

    // Voice record button (teacher)
    const btnTeacherRecord = document.getElementById('btn-teacher-record-voice');
    btnTeacherRecord.addEventListener('click', () => {
        if (!state.isTeacherRecording) {
            startTeacherRecording();
        } else {
            stopTeacherRecording();
        }
    });

    // Results panel actions
    document.getElementById('btn-cancel-results').addEventListener('click', () => {
        document.getElementById('attendance-results-section').classList.add('hidden');
        state.analyzedAttendanceResults = null;
    });

    document.getElementById('btn-save-attendance-submit').addEventListener('click', async () => {
        if (!state.analyzedAttendanceResults) return;
        
        const subjectSelect = document.getElementById('attendance-subject-select');
        const subjectId = parseInt(subjectSelect.value);
        
        const timestamp = new Date().toISOString();
        
        // Compile logs from results table checkbox states
        const logs = state.analyzedAttendanceResults.map(item => {
            const check = document.getElementById(`chk-present-${item.student_id}`);
            return {
                student_id: item.student_id,
                subject_id: subjectId,
                timestamp: timestamp,
                is_present: check ? check.checked : item.is_present
            };
        });

        showToast('Saving attendance check-in to database...', 'info');
        
        try {
            const response = await fetch(`${API_BASE}/teacher/save-attendance`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(logs)
            });
            const data = await response.json();
            
            if (response.ok && data.success) {
                showToast('Attendance logged successfully!', 'success');
                document.getElementById('attendance-results-section').classList.add('hidden');
                
                // Reset inputs
                state.selectedClassroomPhotos = [];
                renderPhotoThumbnails();
                state.analyzedAttendanceResults = null;
            } else {
                showToast(data.detail || 'Save failed', 'error');
            }
        } catch (err) {
            console.error(err);
            showToast('Failed to save logs to database.', 'error');
        }
    });
}

function loadTeacherDashboard() {
    if (!state.teacher) return;
    document.getElementById('teacher-welcome-name').textContent = state.teacher.name;
    loadActiveTeacherTabContent();
}

function loadActiveTeacherTabContent() {
    if (state.activeTeacherTab === 'tab-take-attendance') {
        populateTeacherSubjectsDropdown();
    } else if (state.activeTeacherTab === 'tab-manage-subjects') {
        loadTeacherSubjectsGrid();
    } else if (state.activeTeacherTab === 'tab-attendance-records') {
        loadTeacherAttendanceRecords();
    }
}

// Subj Dropdown
async function populateTeacherSubjectsDropdown() {
    try {
        const response = await fetch(`${API_BASE}/teacher/${state.teacher.teacher_id}/subjects`);
        if (!response.ok) throw new Error('Failed to fetch subjects');
        const subjects = await response.json();
        
        state.teacherSubjects = subjects;
        
        const select = document.getElementById('attendance-subject-select');
        select.innerHTML = '<option value="">-- Choose Subject --</option>';
        
        subjects.forEach(sub => {
            const opt = document.createElement('option');
            opt.value = sub.subject_id;
            opt.textContent = `${sub.name} - ${sub.subject_code} (Sec ${sub.section})`;
            select.appendChild(opt);
        });
    } catch (err) {
        console.error(err);
        showToast('Failed to load courses list.', 'error');
    }
}

// Handles selecting photos for face analysis
function handleClassroomPhotosSelect(files) {
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        if (file.type.startsWith('image/')) {
            state.selectedClassroomPhotos.push(file);
        }
    }
    renderPhotoThumbnails();
}

function renderPhotoThumbnails() {
    const grid = document.getElementById('photo-thumbnail-grid');
    const container = document.getElementById('selected-photos-section');
    const countSpan = document.getElementById('photo-count');
    
    grid.innerHTML = '';
    countSpan.textContent = state.selectedClassroomPhotos.length;
    
    if (state.selectedClassroomPhotos.length === 0) {
        container.classList.add('hidden');
        return;
    }
    
    container.classList.remove('hidden');
    
    state.selectedClassroomPhotos.forEach((file, index) => {
        const thumb = document.createElement('div');
        thumb.className = 'photo-thumb';
        thumb.innerHTML = `
            <img src="${URL.createObjectURL(file)}" alt="Classroom snapshot">
            <button class="photo-thumb-remove" data-index="${index}">&times;</button>
        `;
        grid.appendChild(thumb);
    });

    // Remove event handles
    document.querySelectorAll('.photo-thumb-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const index = parseInt(e.currentTarget.dataset.index);
            state.selectedClassroomPhotos.splice(index, 1);
            renderPhotoThumbnails();
        });
    });
}

// Injects results inside verified table
function renderAnalysisResults(results) {
    const section = document.getElementById('attendance-results-section');
    const tbody = document.getElementById('results-table-body');
    
    tbody.innerHTML = '';
    section.classList.remove('hidden');
    
    if (results.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-secondary)">No enrolled students identified in photos.</td></tr>`;
        return;
    }

    results.forEach(item => {
        const badge = item.is_present 
            ? `<span class="badge badge-present"><span class="material-symbols-rounded" style="font-size:16px">check_circle</span> Present</span>`
            : `<span class="badge badge-absent"><span class="material-symbols-rounded" style="font-size:16px">cancel</span> Absent</span>`;
            
        const sources = item.sources && item.sources.length > 0 ? item.sources.join(', ') : 'Not recognized';
        const checkbox = `<input type="checkbox" id="chk-present-${item.student_id}" ${item.is_present ? 'checked' : ''} style="transform:scale(1.2); cursor:pointer;">`;
        
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>#${item.student_id}</td>
            <td style="font-weight:600">${item.name}</td>
            <td style="font-size:0.85rem; color:var(--text-secondary)">${sources}</td>
            <td>
                <div style="display:flex; align-items:center; gap:12px">
                    ${checkbox}
                    ${badge}
                </div>
            </td>
        `;
        tbody.appendChild(tr);
        
        // Listen to checkbox toggle to change badge color dynamically
        const chk = tr.querySelector('input[type="checkbox"]');
        chk.addEventListener('change', (e) => {
            const badgeContainer = tr.querySelector('.badge');
            if (e.target.checked) {
                badgeContainer.className = 'badge badge-present';
                badgeContainer.innerHTML = '<span class="material-symbols-rounded" style="font-size:16px">check_circle</span> Present';
            } else {
                badgeContainer.className = 'badge badge-absent';
                badgeContainer.innerHTML = '<span class="material-symbols-rounded" style="font-size:16px">cancel</span> Absent';
            }
        });
    });
}

// Teacher voice recorders
async function startTeacherRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        state.teacherAudioChunks = [];
        
        state.teacherVoiceRecorder = new MediaRecorder(stream);
        state.teacherVoiceRecorder.ondataavailable = (event) => {
            state.teacherAudioChunks.push(event.data);
        };
        
        state.teacherVoiceRecorder.onstop = async () => {
            state.teacherVoiceBlob = new Blob(state.teacherAudioChunks, { type: 'audio/wav' });
            stream.getTracks().forEach(track => track.stop());
            
            // Run analysis immediately
            await runVoiceRollCallAnalysis(state.teacherVoiceBlob);
        };
        
        state.teacherVoiceRecorder.start();
        state.isTeacherRecording = true;
        
        // UI
        document.getElementById('teacher-record-text').textContent = 'Stop Recording';
        document.getElementById('teacher-mic-icon').textContent = 'stop';
        document.getElementById('teacher-recording-indicator').classList.remove('hidden');
        
        let seconds = 0;
        const timerSpan = document.getElementById('teacher-voice-timer');
        state.teacherTimerInterval = setInterval(() => {
            seconds++;
            const m = String(Math.floor(seconds / 60)).padStart(2, '0');
            const s = String(seconds % 60).padStart(2, '0');
            timerSpan.textContent = `${m}:${s}`;
        }, 1000);
        
    } catch (err) {
        console.error(err);
        showToast('Could not record. Microphone access denied.', 'error');
    }
}

function stopTeacherRecording() {
    if (state.teacherVoiceRecorder && state.isTeacherRecording) {
        state.teacherVoiceRecorder.stop();
        state.isTeacherRecording = false;
        
        clearInterval(state.teacherTimerInterval);
        state.teacherTimerInterval = null;
        
        // UI reset
        document.getElementById('teacher-record-text').textContent = 'Start Live Recording';
        document.getElementById('teacher-mic-icon').textContent = 'mic';
        document.getElementById('teacher-recording-indicator').classList.add('hidden');
    }
}

async function runVoiceRollCallAnalysis(audioBlob) {
    const subjectSelect = document.getElementById('attendance-subject-select');
    const subjectId = subjectSelect.value;
    
    if (!subjectId) {
        showToast('Please select a subject first!', 'warning');
        return;
    }

    const formData = new FormData();
    formData.append('subject_id', subjectId);
    formData.append('audio', audioBlob, 'classroom_rollcall.wav');

    showToast('Running Voice Biometric roll call checks...', 'info');
    
    try {
        const response = await fetch(`${API_BASE}/teacher/take-attendance-voice`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        if (response.ok && data.success) {
            // Map confidence details for display
            const results = data.results.map(item => ({
                student_id: item.student_id,
                name: item.name,
                is_present: item.is_present,
                sources: item.is_present ? `Voice Recognized (Score: ${Math.round(item.confidence * 100)}%)` : 'Silence/No Match'
            }));
            
            state.analyzedAttendanceResults = results;
            renderAnalysisResults(results);
        } else {
            showToast(data.detail || 'Voice analysis failed', 'error');
        }
    } catch (err) {
        console.error(err);
        showToast('Server connection failed.', 'error');
    }
}

// --- Tab B: Manage Subjects ---
async function loadTeacherSubjectsGrid() {
    try {
        const response = await fetch(`${API_BASE}/teacher/${state.teacher.teacher_id}/subjects`);
        if (!response.ok) throw new Error('Data fetch failed');
        const subjects = await response.json();
        
        const grid = document.getElementById('teacher-subjects-grid');
        grid.innerHTML = '';
        
        if (subjects.length === 0) {
            grid.innerHTML = `
                <div class="glass-panel" style="grid-column:1/-1; padding:40px; text-align:center; color:var(--text-secondary)">
                    <span class="material-symbols-rounded" style="font-size:3rem; margin-bottom:10px; color:var(--text-muted)">library_books</span>
                    <p>No subjects found. Click "Create New Subject" to configure one.</p>
                </div>
            `;
            return;
        }

        subjects.forEach(sub => {
            const card = document.createElement('div');
            card.className = 'subject-card';
            card.innerHTML = `
                <div class="course-info">
                    <h4>${sub.name}</h4>
                    <span class="course-code">📘 Code: ${sub.subject_code} • Sec ${sub.section}</span>
                </div>
                <div class="course-card-metrics" style="margin-bottom:0">
                    <div>
                        <span class="card-metric-num">${sub.total_students}</span>
                        <span class="card-metric-lbl">Students Enrolled</span>
                    </div>
                    <div>
                        <span class="card-metric-num">${sub.total_classes}</span>
                        <span class="card-metric-lbl">Sessions Logged</span>
                    </div>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (err) {
        console.error(err);
        showToast('Failed to load courses.', 'error');
    }
}

// --- Tab C: Attendance Records Logs ---
async function loadTeacherAttendanceRecords() {
    try {
        const response = await fetch(`${API_BASE}/teacher/${state.teacher.teacher_id}/attendance`);
        if (!response.ok) throw new Error('Records fetch failed');
        const records = await response.json();
        
        const tbody = document.getElementById('records-table-body');
        tbody.innerHTML = '';
        
        if (records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-secondary)">No attendance logs recorded yet.</td></tr>`;
            drawAttendanceChart([]);
            return;
        }

        // Group records by unique timestamps
        const sessions = {};
        records.forEach(r => {
            const ts = r.timestamp;
            if (!ts) return;
            
            const groupKey = ts.split('.')[0]; // trim milliseconds
            if (!sessions[groupKey]) {
                sessions[groupKey] = {
                    timestamp: ts,
                    subjectName: r.subjects.name,
                    subjectCode: r.subjects.subject_code,
                    present: 0,
                    total: 0,
                    students: []
                };
            }
            sessions[groupKey].total++;
            if (r.is_present) sessions[groupKey].present++;
            sessions[groupKey].students.push(r);
        });

        // Convert sessions map to sorted list (newest first)
        const sortedSessions = Object.values(sessions).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        
        sortedSessions.forEach(session => {
            const dateStr = new Date(session.timestamp).toLocaleDateString(undefined, {
                month: 'short', day: 'numeric', year: 'numeric',
                hour: '2-digit', minute: '2-digit'
            });
            const ratio = `${session.present} / ${session.total}`;
            const percentage = session.total > 0 ? Math.round((session.present / session.total) * 100) : 0;
            
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-weight:500">${dateStr}</td>
                <td>${session.subjectName}</td>
                <td style="font-family:var(--font-heading)">${session.subjectCode}</td>
                <td>
                    <span class="badge ${percentage > 70 ? 'badge-present' : 'badge-absent'}" style="font-weight:700">
                        ${ratio} (${percentage}%)
                    </span>
                </td>
                <td>
                    <button class="btn btn-secondary btn-icon btn-session-detail" data-key="${session.timestamp}">
                        <span class="material-symbols-rounded">visibility</span> Details
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });

        // Store sessions globally on window for modal reference access
        window.activeTeacherSessions = sessions;
        
        // Listen to detail click
        document.querySelectorAll('.btn-session-detail').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tsKey = e.currentTarget.dataset.key;
                openSessionDetailModal(tsKey);
            });
        });

        // Draw trend SVG chart
        drawAttendanceChart(sortedSessions);
        
        // Setup table search filtering
        const searchInput = document.getElementById('record-search');
        searchInput.addEventListener('input', (e) => {
            const val = e.target.value.toLowerCase();
            const rows = tbody.querySelectorAll('tr');
            rows.forEach(row => {
                const subText = row.cells[1].textContent.toLowerCase();
                const codeText = row.cells[2].textContent.toLowerCase();
                if (subText.includes(val) || codeText.includes(val)) {
                    row.classList.remove('hidden');
                } else {
                    row.classList.add('hidden');
                }
            });
        });

    } catch (err) {
        console.error(err);
        showToast('Failed to load logs list.', 'error');
    }
}

// Draws a premium custom SVG line graph of recent check-ins
function drawAttendanceChart(sessions) {
    const svg = document.getElementById('analytics-svg');
    svg.innerHTML = '';
    
    if (sessions.length === 0) {
        svg.innerHTML = `<text x="400" y="125" fill="var(--text-muted)" text-anchor="middle" font-size="16">Collect logs to view trend graphs</text>`;
        return;
    }

    // Limit to latest 7 sessions and reverse for chronological left-to-right plotting
    const chartData = sessions.slice(0, 7).reverse();
    
    const width = 800;
    const height = 250;
    const paddingX = 80;
    const paddingY = 40;
    
    const chartWidth = width - paddingX * 2;
    const chartHeight = height - paddingY * 2;
    
    // Draw background grid lines (horizontal 0%, 25%, 50%, 75%, 100%)
    for (let i = 0; i <= 4; i++) {
        const y = paddingY + (chartHeight * i) / 4;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', paddingX);
        line.setAttribute('y1', y);
        line.setAttribute('x2', width - paddingX);
        line.setAttribute('y2', y);
        line.setAttribute('stroke', 'rgba(255, 255, 255, 0.04)');
        line.setAttribute('stroke-width', '1');
        svg.appendChild(line);
        
        // Percent labels
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', paddingX - 15);
        text.setAttribute('y', y + 4);
        text.setAttribute('fill', 'var(--text-muted)');
        text.setAttribute('font-size', '11');
        text.setAttribute('text-anchor', 'end');
        text.textContent = `${100 - i * 25}%`;
        svg.appendChild(text);
    }

    const points = [];
    chartData.forEach((session, index) => {
        const percent = session.total > 0 ? (session.present / session.total) * 100 : 0;
        
        const x = paddingX + (chartWidth * index) / Math.max(1, chartData.length - 1);
        const y = paddingY + chartHeight - (chartHeight * percent) / 100;
        points.push({ x, y, percent, label: session.subjectCode, rawDate: session.timestamp });
    });

    // Create glowing neon line shadow path
    if (points.length > 1) {
        let pathD = `M ${points[0].x} ${points[0].y}`;
        for (let i = 1; i < points.length; i++) {
            // Cubic bezier bezier curving for smooth curves
            const cpX1 = points[i-1].x + (points[i].x - points[i-1].x) / 2;
            const cpY1 = points[i-1].y;
            const cpX2 = points[i-1].x + (points[i].x - points[i-1].x) / 2;
            const cpY2 = points[i].y;
            pathD += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${points[i].x} ${points[i].y}`;
        }
        
        // Glow shadow
        const shadowPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        shadowPath.setAttribute('d', pathD);
        shadowPath.setAttribute('fill', 'none');
        shadowPath.setAttribute('stroke', 'var(--color-primary)');
        shadowPath.setAttribute('stroke-width', '6');
        shadowPath.setAttribute('opacity', '0.25');
        shadowPath.setAttribute('filter', 'blur(6px)');
        svg.appendChild(shadowPath);
        
        // Solid line
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', pathD);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', 'url(#chart-grad)');
        path.setAttribute('stroke-width', '3');
        svg.appendChild(path);
        
        // Define Gradient
        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        defs.innerHTML = `
            <linearGradient id="chart-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="var(--color-primary)" />
                <stop offset="100%" stop-color="var(--color-secondary)" />
            </linearGradient>
        `;
        svg.appendChild(defs);
    }

    // Add nodes/dots & text labels
    points.forEach((pt) => {
        // Dot group
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        
        const outerCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        outerCircle.setAttribute('cx', pt.x);
        outerCircle.setAttribute('cy', pt.y);
        outerCircle.setAttribute('r', '7');
        outerCircle.setAttribute('fill', 'var(--color-primary)');
        outerCircle.setAttribute('opacity', '0.4');
        outerCircle.setAttribute('class', 'chart-dot-pulse');
        g.appendChild(outerCircle);

        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', pt.x);
        circle.setAttribute('cy', pt.y);
        circle.setAttribute('r', '4.5');
        circle.setAttribute('fill', '#ffffff');
        circle.setAttribute('stroke', 'var(--color-secondary)');
        circle.setAttribute('stroke-width', '2');
        g.appendChild(circle);
        
        // Percent text
        const pctText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        pctText.setAttribute('x', pt.x);
        pctText.setAttribute('y', pt.y - 14);
        pctText.setAttribute('fill', 'var(--text-primary)');
        pctText.setAttribute('font-size', '10');
        pctText.setAttribute('font-weight', '700');
        pctText.setAttribute('text-anchor', 'middle');
        pctText.textContent = `${pt.percent}%`;
        g.appendChild(pctText);
        
        // Date bottom label
        const dateObj = new Date(pt.rawDate);
        const dayLabel = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        
        const labelText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        labelText.setAttribute('x', pt.x);
        labelText.setAttribute('y', height - paddingY + 18);
        labelText.setAttribute('fill', 'var(--text-muted)');
        labelText.setAttribute('font-size', '10');
        labelText.setAttribute('text-anchor', 'middle');
        labelText.textContent = dayLabel;
        g.appendChild(labelText);

        // Subject Code label
        const codeText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        codeText.setAttribute('x', pt.x);
        codeText.setAttribute('y', height - paddingY + 30);
        codeText.setAttribute('fill', 'var(--text-secondary)');
        codeText.setAttribute('font-size', '9');
        codeText.setAttribute('font-weight', '600');
        codeText.setAttribute('text-anchor', 'middle');
        codeText.textContent = pt.label;
        g.appendChild(codeText);

        svg.appendChild(g);
    });
}

// ==================== DIALOGS & MODALS MANAGEMENT ====================
function initModals() {
    // Close handles
    document.getElementById('btn-close-enroll-modal').addEventListener('click', () => closeModal('modal-enroll'));
    document.getElementById('btn-close-subject-modal').addEventListener('click', () => closeModal('modal-create-subject'));
    document.getElementById('btn-cancel-create-subject').addEventListener('click', () => closeModal('modal-create-subject'));
    document.getElementById('btn-close-detail-modal').addEventListener('click', () => closeModal('modal-session-detail'));

    // Create Subject Form
    const createSubForm = document.getElementById('form-create-subject');
    createSubForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const name = document.getElementById('new-subject-name').value.trim();
        const subject_code = document.getElementById('new-subject-code').value.trim();
        const section = document.getElementById('new-subject-section').value.trim();
        
        showToast('Creating subject...', 'info');
        
        try {
            const response = await fetch(`${API_BASE}/teacher/subjects/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name, subject_code, section,
                    teacher_id: state.teacher.teacher_id
                })
            });
            const data = await response.json();
            
            if (response.ok && data.success) {
                showToast(`Subject ${data.subject.name} created!`, 'success');
                closeModal('modal-create-subject');
                createSubForm.reset();
                loadTeacherSubjectsGrid();
            } else {
                showToast(data.detail || 'Creation failed', 'error');
            }
        } catch (err) {
            console.error(err);
            showToast('Failed to create course.', 'error');
        }
    });

    document.getElementById('btn-open-create-subject').addEventListener('click', () => {
        openModal('modal-create-subject');
    });
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('hidden');
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('hidden');
}

// Student catalog modal populate
async function openEnrollmentModal() {
    if (!state.student) return;
    openModal('modal-enroll');
    
    try {
        const response = await fetch(`${API_BASE}/student/${state.student.student_id}/available-subjects`);
        if (!response.ok) throw new Error('Failed to fetch available catalog');
        const subjects = await response.json();
        
        const tbody = document.getElementById('enroll-catalog-body');
        tbody.innerHTML = '';
        
        if (subjects.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-secondary)">No additional subjects available for enrollment.</td></tr>`;
            return;
        }

        subjects.forEach(sub => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-family:var(--font-heading); font-weight:600">${sub.subject_code}</td>
                <td style="font-weight:500">${sub.name}</td>
                <td>Section ${sub.section}</td>
                <td>${sub.teachers ? sub.teachers.name : 'Unknown'}</td>
                <td>
                    <button class="btn btn-primary btn-icon btn-enroll-action" data-id="${sub.subject_id}">
                        <span class="material-symbols-rounded" style="font-size:16px">add</span> Enroll
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });

        // Hook buttons
        document.querySelectorAll('.btn-enroll-action').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const subjectId = e.currentTarget.dataset.id;
                await enrollStudentInSubject(subjectId);
            });
        });

    } catch (err) {
        console.error(err);
        showToast('Failed to load courses catalog.', 'error');
    }
}

async function enrollStudentInSubject(subjectId) {
    try {
        const response = await fetch(`${API_BASE}/student/enroll`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                student_id: state.student.student_id,
                subject_id: parseInt(subjectId)
            })
        });
        const data = await response.json();
        if (response.ok && data.success) {
            showToast('Enrolled successfully!', 'success');
            closeModal('modal-enroll');
            loadStudentDashboard();
        } else {
            showToast(data.detail || 'Enrollment failed', 'error');
        }
    } catch (err) {
        console.error(err);
        showToast('Connection failed.', 'error');
    }
}

// Session Detail modal popup (Teacher records)
function openSessionDetailModal(tsKey) {
    const sessions = window.activeTeacherSessions;
    if (!sessions || !sessions[tsKey.split('.')[0]]) return;
    
    const session = sessions[tsKey.split('.')[0]];
    
    document.getElementById('detail-session-subject').textContent = `${session.subjectName} (${session.subjectCode})`;
    
    const dateStr = new Date(session.timestamp).toLocaleDateString(undefined, {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
    document.getElementById('detail-session-time').textContent = dateStr;
    
    const tbody = document.getElementById('detail-session-body');
    tbody.innerHTML = '';
    
    // Fetch detailed student profiles matching this session key
    session.students.forEach(row => {
        // Fetch student name from row.students (Supabase nested objects load)
        const name = row.students ? row.students.name : 'Unknown Student';
        
        const badge = row.is_present 
            ? `<span class="badge badge-present"><span class="material-symbols-rounded" style="font-size:16px">check_circle</span> Present</span>`
            : `<span class="badge badge-absent"><span class="material-symbols-rounded" style="font-size:16px">cancel</span> Absent</span>`;
            
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>#${row.student_id}</td>
            <td style="font-weight:600">${name}</td>
            <td>${badge}</td>
        `;
        tbody.appendChild(tr);
    });
    
    openModal('modal-session-detail');
}
