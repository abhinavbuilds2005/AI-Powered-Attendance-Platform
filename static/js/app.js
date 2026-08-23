// PresentAI Application Logic

let currentStudent = null;
let currentTeacher = null;
let stagedPhotos = [];
let studentCameraStream = null;
let regCameraStream = null;
let classroomCameraStream = null;
let voiceRecordTimerInterval = null;
let voiceRecordSeconds = 0;
let pendingAttendanceLogs = [];

// ==================== UNIVERSAL 16kHz PCM WAV RECORDER ==================== //
class WavAudioRecorder {
  constructor() {
    this.audioContext = null;
    this.mediaStream = null;
    this.processor = null;
    this.input = null;
    this.leftchannel = [];
    this.recordingLength = 0;
    this.sampleRate = 16000;
    this.isRecording = false;
  }

  async start() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    this.audioContext = new AudioContextClass({ sampleRate: this.sampleRate });
    this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: this.sampleRate } });
    this.input = this.audioContext.createMediaStreamSource(this.mediaStream);
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
    this.leftchannel = [];
    this.recordingLength = 0;
    this.isRecording = true;

    this.processor.onaudioprocess = (e) => {
      if (!this.isRecording) return;
      const channel = e.inputBuffer.getChannelData(0);
      this.leftchannel.push(new Float32Array(channel));
      this.recordingLength += channel.length;
    };

    this.input.connect(this.processor);
    this.processor.connect(this.audioContext.destination);
  }

  async stop() {
    this.isRecording = false;
    if (this.processor && this.input) {
      this.processor.disconnect();
      this.input.disconnect();
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
    }
    if (this.audioContext && this.audioContext.state !== 'closed') {
      await this.audioContext.close();
    }

    // Flatten samples into 1 array
    const flatSamples = new Float32Array(this.recordingLength);
    let offset = 0;
    for (let i = 0; i < this.leftchannel.length; i++) {
      flatSamples.set(this.leftchannel[i], offset);
      offset += this.leftchannel[i].length;
    }

    // Create 16-bit PCM WAV File Buffer
    const buffer = new ArrayBuffer(44 + flatSamples.length * 2);
    const view = new DataView(buffer);

    function writeString(v, off, str) {
      for (let j = 0; j < str.length; j++) {
        v.setUint8(off + j, str.charCodeAt(j));
      }
    }

    // RIFF header
    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + flatSamples.length * 2, true);
    writeString(view, 8, 'WAVE');
    // FMT sub-chunk
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM format
    view.setUint16(22, 1, true); // Mono channel
    view.setUint32(24, 16000, true); // 16kHz
    view.setUint32(28, 32000, true); // Byte rate (16000 * 2)
    view.setUint16(32, 2, true); // Block align
    view.setUint16(34, 16, true); // 16 bits per sample
    // Data sub-chunk
    writeString(view, 36, 'data');
    view.setUint32(40, flatSamples.length * 2, true);

    // Write PCM 16-bit samples
    let index = 44;
    for (let i = 0; i < flatSamples.length; i++) {
      const s = Math.max(-1, Math.min(1, flatSamples[i]));
      view.setInt16(index, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      index += 2;
    }

    const blob = new Blob([view], { type: 'audio/wav' });
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.readAsDataURL(blob);
    });
  }
}

// Global recorder instances
let studentRegRecorder = null;
let studentAuthRecorder = null;
let classroomRecorder = null;
let recordedVoiceBase64 = null;
let classroomRecordedVoiceB64 = null;

// ==================== VIEW MANAGEMENT ==================== //
function showView(viewId) {
  stopAllCameras();
  document.querySelectorAll('.view-section').forEach(el => el.style.display = 'none');
  const target = document.getElementById(`view-${viewId}`);
  if (target) target.style.display = 'block';
  updateHeaderNav();
}
window.showView = showView;

function updateHeaderNav() {
  const navArea = document.getElementById('nav-user-area');
  if (!navArea) return;
  if (currentStudent) {
    navArea.innerHTML = `
      <span class="badge badge-info"><span class="material-symbols-outlined" style="font-size: 16px;">person</span> ${currentStudent.name}</span>
      <button class="btn btn-secondary" style="padding: 0.4rem 0.8rem; font-size: 0.85rem;" onclick="logoutStudent()">Log Out</button>
    `;
  } else if (currentTeacher) {
    navArea.innerHTML = `
      <span class="badge badge-info"><span class="material-symbols-outlined" style="font-size: 16px;">school</span> ${currentTeacher.name}</span>
      <button class="btn btn-secondary" style="padding: 0.4rem 0.8rem; font-size: 0.85rem;" onclick="logoutTeacher()">Log Out</button>
    `;
  } else {
    navArea.innerHTML = '';
  }
}
window.updateHeaderNav = updateHeaderNav;

// ==================== TOAST & MODAL HELPERS ==================== //
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.style.borderLeft = type === 'error' ? '4px solid var(--danger)' : (type === 'success' ? '4px solid var(--success)' : '4px solid var(--primary)');
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => { toast.remove(); }, 3500);
}
window.showToast = showToast;

function openModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) el.classList.add('show');
}
window.openModal = openModal;

function closeModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) el.classList.remove('show');
  if (modalId === 'modal-webcam-snapshot') {
    stopStream(classroomCameraStream);
    classroomCameraStream = null;
  }
}
window.closeModal = closeModal;

// ==================== CAMERA CONTROLLER ==================== //
async function startStudentCamera() {
  try {
    const video = document.getElementById('student-video');
    if (!video) return;
    studentCameraStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
    });
    video.srcObject = studentCameraStream;
  } catch (err) {
    showToast('Unable to access webcam. Check browser permissions.', 'error');
  }
}
window.startStudentCamera = startStudentCamera;

async function startRegistrationCamera() {
  try {
    const video = document.getElementById('reg-student-video');
    if (!video) return;
    regCameraStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
    });
    video.srcObject = regCameraStream;
  } catch (err) {
    showToast('Unable to access webcam for registration.', 'error');
  }
}
window.startRegistrationCamera = startRegistrationCamera;

function stopStream(stream) {
  if (stream) {
    stream.getTracks().forEach(track => track.stop());
  }
}

function stopAllCameras() {
  stopStream(studentCameraStream);
  stopStream(regCameraStream);
  stopStream(classroomCameraStream);
  studentCameraStream = null;
  regCameraStream = null;
  classroomCameraStream = null;
}
window.stopAllCameras = stopAllCameras;

function captureFrameAsBase64(videoElement, canvasElement) {
  const width = videoElement.videoWidth || 640;
  const height = videoElement.videoHeight || 480;
  canvasElement.width = width;
  canvasElement.height = height;
  const ctx = canvasElement.getContext('2d');
  ctx.drawImage(videoElement, 0, 0, width, height);
  return canvasElement.toDataURL('image/jpeg', 0.9);
}

// ==================== STUDENT PORTAL & BIOMETRIC AUTH ==================== //
function openStudentPortal() {
  showView('student-portal');
  switchStudentMainTab('login');
}
window.openStudentPortal = openStudentPortal;

function switchStudentMainTab(tab) {
  const loginSec = document.getElementById('student-login-section');
  const regSec = document.getElementById('student-register-section');
  const tabLogin = document.getElementById('s-main-tab-login');
  const tabReg = document.getElementById('s-main-tab-register');

  if (tab === 'login') {
    if (loginSec) loginSec.style.display = 'block';
    if (regSec) regSec.style.display = 'none';
    if (tabLogin) tabLogin.classList.add('active');
    if (tabReg) tabReg.classList.remove('active');
    stopStream(regCameraStream);
    regCameraStream = null;
    switchStudentAuthMode('face');
  } else {
    if (loginSec) loginSec.style.display = 'none';
    if (regSec) regSec.style.display = 'block';
    if (tabLogin) tabLogin.classList.remove('active');
    if (tabReg) tabReg.classList.add('active');
    stopStream(studentCameraStream);
    studentCameraStream = null;
    startRegistrationCamera();
  }
}
window.switchStudentMainTab = switchStudentMainTab;

function switchStudentAuthMode(mode) {
  const faceContainer = document.getElementById('student-face-container');
  const voiceContainer = document.getElementById('student-voice-container');
  const tabFace = document.getElementById('s-tab-face');
  const tabVoice = document.getElementById('s-tab-voice');

  if (mode === 'face') {
    if (faceContainer) faceContainer.style.display = 'block';
    if (voiceContainer) voiceContainer.style.display = 'none';
    if (tabFace) tabFace.classList.add('active');
    if (tabVoice) tabVoice.classList.remove('active');
    startStudentCamera();
  } else {
    stopStream(studentCameraStream);
    studentCameraStream = null;
    if (faceContainer) faceContainer.style.display = 'none';
    if (voiceContainer) voiceContainer.style.display = 'block';
    if (tabFace) tabFace.classList.remove('active');
    if (tabVoice) tabVoice.classList.add('active');
  }
}
window.switchStudentAuthMode = switchStudentAuthMode;

async function captureAndFaceLogin() {
  const video = document.getElementById('student-video');
  const canvas = document.getElementById('student-canvas');
  const btn = document.getElementById('btn-student-scan');

  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined">sync</span> Scanning FaceID...';

  const base64Image = captureFrameAsBase64(video, canvas);

  try {
    const res = await fetch('/api/student/face-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: base64Image })
    });
    const data = await res.json();

    if (data.success && data.student) {
      currentStudent = data.student;
      showToast(`Welcome back, ${data.student.name}!`, 'success');
      loadStudentDashboard();
    } else {
      showToast(data.message || 'Face not recognized.', 'error');
      if (data.status === 'unrecognized') {
        window.lastCapturedFaceB64 = base64Image;
        const msg = document.getElementById('reg-face-preview-msg');
        if (msg) msg.innerText = '✅ Face photo automatically imported from scan!';
        switchStudentMainTab('register');
      }
    }
  } catch (err) {
    showToast('Network error scanning face.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined">photo_camera</span> Scan & Authenticate FaceID';
  }
}
window.captureAndFaceLogin = captureAndFaceLogin;

// Student Registration Face Capture
function captureRegistrationFace() {
  const video = document.getElementById('reg-student-video');
  const canvas = document.getElementById('reg-student-canvas');
  const msg = document.getElementById('reg-face-preview-msg');
  const btnLabel = document.getElementById('reg-snap-label');

  if (!video || !canvas) return;
  const b64 = captureFrameAsBase64(video, canvas);
  window.lastCapturedFaceB64 = b64;
  if (msg) msg.innerText = '✅ Face photo captured successfully!';
  if (btnLabel) btnLabel.innerText = 'Retake Face Photo';
  showToast('Face photo snapped!', 'success');
}
window.captureRegistrationFace = captureRegistrationFace;

// Student VoiceID Authentication with 16kHz PCM WAV
let studentAuthTimerInterval = null;
let studentAuthSeconds = 0;

async function toggleStudentVoiceAuth() {
  const micIcon = document.getElementById('s-mic-icon');
  const micLabel = document.getElementById('s-mic-label');
  const timer = document.getElementById('s-voice-timer');

  if (studentAuthRecorder && studentAuthRecorder.isRecording) {
    micIcon.innerText = 'sync';
    micLabel.innerText = 'Matching Voiceprint...';
    clearInterval(studentAuthTimerInterval);

    try {
      const wavBase64 = await studentAuthRecorder.stop();
      studentAuthRecorder = null;
      await sendStudentVoiceLogin(wavBase64);
    } catch (err) {
      showToast('Error finalizing voice recording.', 'error');
    } finally {
      micIcon.innerText = 'mic';
      micLabel.innerText = 'Record Voice to Authenticate';
    }
  } else {
    try {
      studentAuthRecorder = new WavAudioRecorder();
      await studentAuthRecorder.start();

      micIcon.innerText = 'stop';
      micLabel.innerText = 'Stop & Authenticate';
      studentAuthSeconds = 0;
      timer.innerText = '00:00';
      studentAuthTimerInterval = setInterval(() => {
        studentAuthSeconds++;
        const mins = String(Math.floor(studentAuthSeconds / 60)).padStart(2, '0');
        const secs = String(studentAuthSeconds % 60).padStart(2, '0');
        timer.innerText = `${mins}:${secs}`;
      }, 1000);
    } catch (err) {
      showToast('Microphone access denied.', 'error');
    }
  }
}
window.toggleStudentVoiceAuth = toggleStudentVoiceAuth;

async function sendStudentVoiceLogin(base64Audio) {
  try {
    const res = await fetch('/api/student/voice-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audio: base64Audio })
    });
    const data = await res.json();
    if (res.ok && data.success && data.student) {
      currentStudent = data.student;
      showToast(data.message || `Welcome, ${data.student.name}!`, 'success');
      loadStudentDashboard();
    } else {
      showToast(data.message || 'Voice not recognized.', 'error');
    }
  } catch (err) {
    showToast('Network error during voice authentication.', 'error');
  }
}

// Student Registration Voice Sample with 16kHz PCM WAV
async function toggleVoiceRecording() {
  const micIcon = document.getElementById('mic-icon');
  const micLabel = document.getElementById('mic-label');
  const timer = document.getElementById('voice-timer');

  if (studentRegRecorder && studentRegRecorder.isRecording) {
    clearInterval(voiceRecordTimerInterval);
    micIcon.innerText = 'sync';
    micLabel.innerText = 'Processing Sample...';

    try {
      recordedVoiceBase64 = await studentRegRecorder.stop();
      studentRegRecorder = null;
      const preview = document.getElementById('reg-voice-preview');
      if (preview) {
        preview.src = recordedVoiceBase64;
        preview.style.display = 'block';
      }
      micIcon.innerText = 'mic';
      micLabel.innerText = 'Record Again';
      showToast('Voice sample recorded successfully!', 'success');
    } catch (err) {
      showToast('Error recording voice sample.', 'error');
    }
  } else {
    try {
      studentRegRecorder = new WavAudioRecorder();
      await studentRegRecorder.start();

      micIcon.innerText = 'stop';
      micLabel.innerText = 'Stop Recording';
      voiceRecordSeconds = 0;
      timer.innerText = '00:00';
      voiceRecordTimerInterval = setInterval(() => {
        voiceRecordSeconds++;
        const mins = String(Math.floor(voiceRecordSeconds / 60)).padStart(2, '0');
        const secs = String(voiceRecordSeconds % 60).padStart(2, '0');
        timer.innerText = `${mins}:${secs}`;
      }, 1000);
    } catch (err) {
      showToast('Microphone access denied.', 'error');
    }
  }
}
window.toggleVoiceRecording = toggleVoiceRecording;

async function submitStudentRegistration() {
  const name = document.getElementById('reg-student-name').value.trim();
  const faceImage = window.lastCapturedFaceB64;

  if (!name) {
    showToast('Please enter your full official name.', 'error');
    return;
  }
  if (!faceImage) {
    showToast('Please snap your face photo using the camera viewfinder.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/student/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        image: faceImage,
        audio: recordedVoiceBase64
      })
    });
    const data = await res.json();
    if (data.success && data.student) {
      currentStudent = data.student;
      showToast(data.message || 'Profile created successfully!', 'success');
      loadStudentDashboard();
    } else {
      showToast(data.detail || 'Registration failed.', 'error');
    }
  } catch (err) {
    showToast('Network error creating profile.', 'error');
  }
}
window.submitStudentRegistration = submitStudentRegistration;

// ==================== STUDENT DASHBOARD ==================== //
async function loadStudentDashboard() {
  showView('student-dashboard');
  document.getElementById('student-name-display').innerText = currentStudent.name;

  try {
    const res = await fetch(`/api/student/${currentStudent.student_id}/courses`);
    const data = await res.json();
    
    const courses = data.courses || [];
    let totalAttended = 0;
    let totalSessions = 0;

    courses.forEach(c => {
      totalAttended += c.attended_sessions;
      totalSessions += c.total_sessions;
    });

    const overallRate = totalSessions > 0 ? Math.round((totalAttended / totalSessions) * 100) : 0;

    document.getElementById('metric-student-courses').innerText = courses.length;
    document.getElementById('metric-student-attended').innerHTML = `${totalAttended} <span style="font-size: 1rem; color: var(--text-muted);">/ ${totalSessions}</span>`;
    document.getElementById('metric-student-rate').innerText = `${overallRate}%`;

    const grid = document.getElementById('student-courses-grid');
    if (courses.length === 0) {
      grid.innerHTML = '<p style="color: var(--text-muted); grid-column: 1/-1;">You are not enrolled in any courses yet. Click "Enroll in Course" above.</p>';
      return;
    }

    grid.innerHTML = courses.map(c => `
      <div class="portal-card" style="text-align: left; align-items: flex-start; border-left: 6px solid var(--primary);">
        <h3 style="margin: 0;">${c.name}</h3>
        <div style="display: flex; gap: 8px; margin: 8px 0; align-items: center;">
          <span class="badge badge-info">${c.subject_code}</span>
          <span style="font-size: 0.85rem; color: var(--text-muted);">Section ${c.section}</span>
        </div>
        <div style="display: flex; gap: 12px; margin: 12px 0;">
          <span class="badge badge-success">✅ ${c.attended_sessions} / ${c.total_sessions} Attended</span>
          <span class="badge badge-info">📊 ${c.attendance_rate}%</span>
        </div>
        <button class="btn btn-danger btn-block" style="margin-top: 8px;" onclick="unenrollCourse(${c.subject_id}, '${c.name}')">
          <span class="material-symbols-outlined">delete</span> Unenroll
        </button>
      </div>
    `).join('');

  } catch (err) {
    showToast('Failed to load courses.', 'error');
  }
}
window.loadStudentDashboard = loadStudentDashboard;

function openEnrollModal() {
  document.getElementById('input-enroll-code').value = '';
  openModal('modal-enroll');
}
window.openEnrollModal = openEnrollModal;

async function submitEnrollment() {
  const code = document.getElementById('input-enroll-code').value.trim();
  if (!code) {
    showToast('Please enter a course code.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/student/enroll', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ student_id: currentStudent.student_id, subject_code: code })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeModal('modal-enroll');
      loadStudentDashboard();
    } else {
      showToast(data.detail || 'Enrollment failed.', 'error');
    }
  } catch (err) {
    showToast('Network error during enrollment.', 'error');
  }
}
window.submitEnrollment = submitEnrollment;

async function unenrollCourse(subjectId, subName) {
  if (!confirm(`Are you sure you want to unenroll from ${subName}?`)) return;

  try {
    const res = await fetch('/api/student/unenroll', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ student_id: currentStudent.student_id, subject_id: subjectId })
    });
    if (res.ok) {
      showToast(`Unenrolled from ${subName}`, 'info');
      loadStudentDashboard();
    }
  } catch (err) {
    showToast('Failed to unenroll.', 'error');
  }
}
window.unenrollCourse = unenrollCourse;

function logoutStudent() {
  currentStudent = null;
  showView('home');
}
window.logoutStudent = logoutStudent;

// ==================== TEACHER AUTH ==================== //
function openTeacherAuth() {
  showView('teacher-auth');
  switchTeacherAuthTab('login');
}
window.openTeacherAuth = openTeacherAuth;

function switchTeacherAuthTab(tab) {
  const loginForm = document.getElementById('teacher-login-form');
  const regForm = document.getElementById('teacher-register-form');
  const loginBtn = document.getElementById('tab-login-btn');
  const regBtn = document.getElementById('tab-reg-btn');

  if (tab === 'login') {
    loginForm.style.display = 'block';
    regForm.style.display = 'none';
    loginBtn.classList.add('active');
    regBtn.classList.remove('active');
  } else {
    loginForm.style.display = 'none';
    regForm.style.display = 'block';
    loginBtn.classList.remove('active');
    regBtn.classList.add('active');
  }
}
window.switchTeacherAuthTab = switchTeacherAuthTab;

async function submitTeacherLogin() {
  const u = document.getElementById('t-login-username').value.trim();
  const p = document.getElementById('t-login-password').value;

  if (!u || !p) {
    showToast('Please enter username and password.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/auth/teacher/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p })
    });
    const data = await res.json();
    if (res.ok && data.teacher) {
      currentTeacher = data.teacher;
      showToast(`Welcome, ${currentTeacher.name}!`, 'success');
      loadTeacherDashboard();
    } else {
      showToast(data.detail || 'Invalid credentials.', 'error');
    }
  } catch (err) {
    showToast('Login network error.', 'error');
  }
}
window.submitTeacherLogin = submitTeacherLogin;

async function submitTeacherRegister() {
  const name = document.getElementById('t-reg-name').value.trim();
  const u = document.getElementById('t-reg-username').value.trim();
  const p = document.getElementById('t-reg-password').value;

  if (!name || !u || !p) {
    showToast('All registration fields are required.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/auth/teacher/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, username: u, password: p })
    });
    const data = await res.json();
    if (res.ok) {
      showToast('Account created! Please sign in.', 'success');
      switchTeacherAuthTab('login');
      document.getElementById('t-login-username').value = u;
    } else {
      showToast(data.detail || 'Registration failed.', 'error');
    }
  } catch (err) {
    showToast('Registration network error.', 'error');
  }
}
window.submitTeacherRegister = submitTeacherRegister;

function logoutTeacher() {
  currentTeacher = null;
  showView('home');
}
window.logoutTeacher = logoutTeacher;

// ==================== TEACHER DASHBOARD ==================== //
async function loadTeacherDashboard() {
  showView('teacher-dashboard');
  document.getElementById('teacher-name-display').innerText = currentTeacher.name;
  switchTeacherTab('take');
  loadTeacherSubjects();
}
window.loadTeacherDashboard = loadTeacherDashboard;

function switchTeacherTab(tab) {
  document.getElementById('teacher-subtab-take').style.display = tab === 'take' ? 'block' : 'none';
  document.getElementById('teacher-subtab-subjects').style.display = tab === 'subjects' ? 'block' : 'none';
  document.getElementById('teacher-subtab-analytics').style.display = tab === 'analytics' ? 'block' : 'none';

  document.getElementById('t-tab-take').className = `tab-btn ${tab === 'take' ? 'active' : ''}`;
  document.getElementById('t-tab-subjects').className = `tab-btn ${tab === 'subjects' ? 'active' : ''}`;
  document.getElementById('t-tab-analytics').className = `tab-btn ${tab === 'analytics' ? 'active' : ''}`;

  if (tab === 'analytics') {
    loadTeacherAnalytics();
  }
}
window.switchTeacherTab = switchTeacherTab;

async function loadTeacherSubjects() {
  try {
    const res = await fetch(`/api/teacher/${currentTeacher.teacher_id}/subjects`);
    const data = await res.json();
    const subjects = data.subjects || [];

    const select = document.getElementById('select-attendance-subject');
    select.innerHTML = subjects.map(s => `
      <option value="${s.subject_id}">${s.name} (${s.subject_code}) - Sec ${s.section}</option>
    `).join('');

    const grid = document.getElementById('teacher-subjects-grid');
    if (subjects.length === 0) {
      grid.innerHTML = '<p style="color: var(--text-muted); grid-column: 1/-1;">No courses created yet. Click "Create New Subject".</p>';
      return;
    }

    grid.innerHTML = subjects.map(s => `
      <div class="portal-card" style="text-align: left; align-items: flex-start; border-left: 6px solid var(--primary);">
        <h3 style="margin: 0;">${s.name}</h3>
        <div style="display: flex; gap: 8px; margin: 8px 0; align-items: center;">
          <span class="badge badge-info">${s.subject_code}</span>
          <span style="font-size: 0.85rem; color: var(--text-muted);">Section ${s.section}</span>
        </div>
        <div style="display: flex; gap: 10px; margin: 12px 0;">
          <span class="badge badge-info">👥 ${s.total_students || 0} Students</span>
          <span class="badge badge-info">🗓️ ${s.total_classes || 0} Sessions</span>
        </div>
        <button class="btn btn-secondary btn-block" onclick="openShareModal('${s.name}', '${s.subject_code}')">
          <span class="material-symbols-outlined">qr_code_2</span> Share Invite QR & Link
        </button>
      </div>
    `).join('');

  } catch (err) {
    showToast('Failed to load courses.', 'error');
  }
}
window.loadTeacherSubjects = loadTeacherSubjects;

function openCreateSubjectModal() {
  document.getElementById('new-sub-code').value = '';
  document.getElementById('new-sub-name').value = '';
  document.getElementById('new-sub-section').value = '';
  openModal('modal-create-subject');
}
window.openCreateSubjectModal = openCreateSubjectModal;

async function submitCreateSubject() {
  const code = document.getElementById('new-sub-code').value.trim();
  const name = document.getElementById('new-sub-name').value.trim();
  const section = document.getElementById('new-sub-section').value.trim();

  if (!code || !name || !section) {
    showToast('All course fields are required.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/teacher/subjects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject_code: code,
        name: name,
        section: section,
        teacher_id: currentTeacher.teacher_id
      })
    });
    if (res.ok) {
      showToast('Course created successfully!', 'success');
      closeModal('modal-create-subject');
      loadTeacherSubjects();
    } else {
      const data = await res.json();
      showToast(data.detail || 'Could not create course.', 'error');
    }
  } catch (err) {
    showToast('Network error creating course.', 'error');
  }
}
window.submitCreateSubject = submitCreateSubject;

function openShareModal(name, code) {
  document.getElementById('share-sub-title').innerText = `Share ${name}`;
  document.getElementById('share-code-display').value = code;
  document.getElementById('share-qr-img').src = `/api/subjects/qr/${code}?host=${window.location.host}`;
  openModal('modal-share-subject');
}
window.openShareModal = openShareModal;

// ==================== CLASSROOM ATTENDANCE PHOTOS & FACE SCAN ==================== //
function handleClassroomPhotosUpload(e) {
  const files = Array.from(e.target.files);
  files.forEach(file => {
    const reader = new FileReader();
    reader.onload = ev => {
      stagedPhotos.push(ev.target.result);
      renderStagedPhotos();
    };
    reader.readAsDataURL(file);
  });
}
window.handleClassroomPhotosUpload = handleClassroomPhotosUpload;

function renderStagedPhotos() {
  const container = document.getElementById('staged-photos-container');
  const grid = document.getElementById('staged-photos-grid');
  const count = document.getElementById('staged-photos-count');

  if (stagedPhotos.length === 0) {
    container.style.display = 'none';
    return;
  }

  container.style.display = 'block';
  count.innerText = `Staged Photos (${stagedPhotos.length})`;

  grid.innerHTML = stagedPhotos.map((src, i) => `
    <div style="position: relative; width: 110px; height: 80px; border-radius: var(--radius-sm); overflow: hidden; border: 1px solid var(--card-border);">
      <img src="${src}" style="width: 100%; height: 100%; object-fit: cover;" />
      <button onclick="removeStagedPhoto(${i})" style="position: absolute; top: 2px; right: 2px; background: rgba(0,0,0,0.6); color: white; border: none; border-radius: 50%; width: 22px; height: 22px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 14px;">✕</button>
    </div>
  `).join('');
}

function removeStagedPhoto(idx) {
  stagedPhotos.splice(idx, 1);
  renderStagedPhotos();
}
window.removeStagedPhoto = removeStagedPhoto;

function clearStagedPhotos() {
  stagedPhotos = [];
  renderStagedPhotos();
}
window.clearStagedPhotos = clearStagedPhotos;

async function openWebcamSnapshotModal() {
  openModal('modal-webcam-snapshot');
  try {
    const video = document.getElementById('classroom-cam-video');
    classroomCameraStream = await navigator.mediaDevices.getUserMedia({ video: true });
    video.srcObject = classroomCameraStream;
  } catch (err) {
    showToast('Camera access denied.', 'error');
  }
}
window.openWebcamSnapshotModal = openWebcamSnapshotModal;

function captureClassroomSnapshot() {
  const video = document.getElementById('classroom-cam-video');
  const canvas = document.getElementById('classroom-cam-canvas');
  const b64 = captureFrameAsBase64(video, canvas);
  stagedPhotos.push(b64);
  renderStagedPhotos();
  closeModal('modal-webcam-snapshot');
  showToast('Classroom snapshot added!', 'success');
}
window.captureClassroomSnapshot = captureClassroomSnapshot;

async function runClassroomFaceScan() {
  const subjectId = parseInt(document.getElementById('select-attendance-subject').value);
  if (!subjectId || stagedPhotos.length === 0) {
    showToast('Please select a course and stage at least 1 photo.', 'error');
    return;
  }

  showToast('AI scanning classroom photos for facial landmarks...', 'info');

  try {
    const res = await fetch('/api/attendance/face-scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject_id: subjectId, images: stagedPhotos })
    });
    const data = await res.json();
    if (res.ok) {
      showAttendanceResultsModal(data.results, data.logs);
    } else {
      showToast(data.detail || 'Scan failed.', 'error');
    }
  } catch (err) {
    showToast('Face scan network error.', 'error');
  }
}
window.runClassroomFaceScan = runClassroomFaceScan;

// ==================== CLASSROOM VOICE ATTENDANCE WITH 16kHz PCM WAV ==================== //
let classroomVoiceTimerInterval = null;
let classroomVoiceSeconds = 0;

function openVoiceAttendanceModal() {
  classroomRecordedVoiceB64 = null;
  document.getElementById('btn-process-voice').disabled = true;
  document.getElementById('t-voice-timer').innerText = '';
  document.getElementById('t-mic-icon').innerText = 'mic';
  document.getElementById('t-mic-label').innerText = 'Start Classroom Recording';
  openModal('modal-voice-attendance');
}
window.openVoiceAttendanceModal = openVoiceAttendanceModal;

async function toggleClassroomVoiceRecording() {
  const micIcon = document.getElementById('t-mic-icon');
  const micLabel = document.getElementById('t-mic-label');
  const timer = document.getElementById('t-voice-timer');
  const processBtn = document.getElementById('btn-process-voice');

  if (classroomRecorder && classroomRecorder.isRecording) {
    clearInterval(classroomVoiceTimerInterval);
    micIcon.innerText = 'sync';
    micLabel.innerText = 'Processing Audio...';

    try {
      classroomRecordedVoiceB64 = await classroomRecorder.stop();
      classroomRecorder = null;
      processBtn.disabled = false;
      micIcon.innerText = 'mic';
      micLabel.innerText = 'Record Again';
      showToast('Classroom audio captured!', 'success');
    } catch (err) {
      showToast('Error capturing classroom audio.', 'error');
    }
  } else {
    try {
      classroomRecorder = new WavAudioRecorder();
      await classroomRecorder.start();

      micIcon.innerText = 'stop';
      micLabel.innerText = 'Stop Recording';
      classroomVoiceSeconds = 0;
      timer.innerText = '00:00';
      classroomVoiceTimerInterval = setInterval(() => {
        classroomVoiceSeconds++;
        const mins = String(Math.floor(classroomVoiceSeconds / 60)).padStart(2, '0');
        const secs = String(classroomVoiceSeconds % 60).padStart(2, '0');
        timer.innerText = `${mins}:${secs}`;
      }, 1000);
    } catch (err) {
      showToast('Microphone access denied.', 'error');
    }
  }
}
window.toggleClassroomVoiceRecording = toggleClassroomVoiceRecording;

async function runVoiceAttendanceScan() {
  const subjectId = parseInt(document.getElementById('select-attendance-subject').value);
  if (!subjectId || !classroomRecordedVoiceB64) {
    showToast('Please record classroom audio first.', 'error');
    return;
  }

  showToast('Extracting acoustic embeddings and matching students...', 'info');

  try {
    const res = await fetch('/api/attendance/voice-scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject_id: subjectId, audio: classroomRecordedVoiceB64 })
    });
    const data = await res.json();
    if (res.ok) {
      closeModal('modal-voice-attendance');
      showAttendanceResultsModal(data.results, data.logs, data.message);
    } else {
      showToast(data.detail || 'Voice scan failed.', 'error');
    }
  } catch (err) {
    showToast('Voice scan network error.', 'error');
  }
}
window.runVoiceAttendanceScan = runVoiceAttendanceScan;

// ==================== ATTENDANCE COMMIT MODAL ==================== //
function showAttendanceResultsModal(results, logs, extraMessage) {
  pendingAttendanceLogs = logs || [];
  const presentCount = results.filter(r => r.is_present).length;
  const totalCount = results.length;

  let msg = `<strong>${presentCount} Present</strong> / ${totalCount - presentCount} Absent out of ${totalCount} enrolled students.`;
  if (extraMessage) {
    msg += `<br/><span style="color: var(--danger); font-size: 0.85rem;">${extraMessage}</span>`;
  }
  document.getElementById('att-results-summary').innerHTML = msg;

  const tbody = document.getElementById('att-results-tbody');
  tbody.innerHTML = results.map(r => `
    <tr>
      <td><strong>${r.name}</strong></td>
      <td>${r.student_id}</td>
      <td style="color: var(--text-muted);">${r.source}</td>
      <td>
        <span class="badge ${r.is_present ? 'badge-success' : 'badge-danger'}">
          ${r.is_present ? '✅ Present' : '❌ Absent'}
        </span>
      </td>
    </tr>
  `).join('');

  openModal('modal-attendance-results');
}
window.showAttendanceResultsModal = showAttendanceResultsModal;

async function commitAttendanceLogs() {
  if (pendingAttendanceLogs.length === 0) {
    showToast('No logs to save.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/attendance/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ logs: pendingAttendanceLogs })
    });
    if (res.ok) {
      showToast('Attendance successfully logged to database!', 'success');
      closeModal('modal-attendance-results');
      clearStagedPhotos();
      loadTeacherSubjects();
    } else {
      const data = await res.json();
      showToast(data.detail || 'Failed to save attendance.', 'error');
    }
  } catch (err) {
    showToast('Network error saving attendance.', 'error');
  }
}
window.commitAttendanceLogs = commitAttendanceLogs;

// ==================== TEACHER ATTENDANCE ANALYTICS & CSV ==================== //
async function loadTeacherAnalytics() {
  try {
    const res = await fetch(`/api/teacher/${currentTeacher.teacher_id}/attendance`);
    const data = await res.json();

    const m = data.metrics || {};
    document.getElementById('t-metric-sessions').innerText = m.total_sessions || 0;
    document.getElementById('t-metric-checks').innerHTML = `${m.total_present || 0} <span style="font-size: 1rem; color: var(--text-muted);">/ ${m.total_students_checked || 0}</span>`;
    document.getElementById('t-metric-rate').innerText = `${m.average_attendance || 0}%`;

    const tbody = document.getElementById('attendance-analytics-tbody');
    const summary = data.summary || [];

    if (summary.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No attendance sessions logged yet.</td></tr>';
      return;
    }

    tbody.innerHTML = summary.map(s => `
      <tr>
        <td><strong>${s.time}</strong></td>
        <td>${s.subject}</td>
        <td><span class="badge badge-info">${s.subject_code}</span></td>
        <td>✅ ${s.present_count} / ${s.total_count} Students</td>
        <td><strong>${s.rate}%</strong></td>
      </tr>
    `).join('');

  } catch (err) {
    showToast('Failed to load analytics.', 'error');
  }
}
window.loadTeacherAnalytics = loadTeacherAnalytics;

function exportAttendanceCSV() {
  if (!currentTeacher) return;
  window.location.href = `/api/teacher/${currentTeacher.teacher_id}/attendance/export`;
}
window.exportAttendanceCSV = exportAttendanceCSV;

// ==================== INITIALIZATION & QUERY PARAMS ==================== //
window.addEventListener('DOMContentLoaded', () => {
  showView('home');

  const params = new URLSearchParams(window.location.search);
  const joinCode = params.get('join-code');
  if (joinCode) {
    openStudentPortal();
    showToast(`Quick enrollment code detected: ${joinCode}`, 'info');
  }
});
