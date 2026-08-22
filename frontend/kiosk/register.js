/**
 * register.js — AttendAI Kiosk Registration client
 * Automatic AI single-face enrollment with smooth scanning effects.
 */

const $ = (id) => document.getElementById(id);


// ═══════════════════════════════════════════════════════════
//  REGISTRATION VARIABLES & SELECTIONS
// ═══════════════════════════════════════════════════════════

const mainContainer = $('mainContainer');
const formScreen = $('formScreen');
const captureScreen = $('captureScreen');
const successScreen = $('successScreen');
const processingScreen = $('processingScreen');

const kioskRegisterForm = $('kioskRegisterForm');
const camImg = $('camImg');
const cameraWaiting = $('cameraWaiting');
const cameraInstruction = $('cameraInstruction');
const btnCapture = $('btnCapture');
const btnDoneReg = $('btnDoneReg');

// Form data temp storage
let regData = {
  userCode: '',
  fullName: '',
  department: ''
};

// Captured photo blob
let capturedBlobs = {
  straight: null,
  left: null,
  right: null
};

// WebSocket and Auto-capture State
let ws = null;
const WS_URL = `ws://${location.host}/ws/attendance`;
let detectStartTime = null;
let isAutoCapturing = false;
let isSubmitting = false;
const CAPTURE_COOLDOWN = 3000; // 3s of continuous detection

// Bounding box state
let _lastBbox = null;


// ═══════════════════════════════════════════════════════════
//  CANVAS BOUNDING BOX
// ═══════════════════════════════════════════════════════════

function drawTargetBox(bbox, isError) {
  const canvas = $('bboxCanvas');
  const img = $('camImg');
  if (!canvas || !img || !img.naturalWidth) return;

  // Match canvas pixel size to the img display size
  canvas.width = img.clientWidth;
  canvas.height = img.clientHeight;

  const containerWidth = canvas.width;
  const containerHeight = canvas.height;
  const naturalWidth = img.naturalWidth || 1280;
  const naturalHeight = img.naturalHeight || 720;

  // Calculate cover scaling factors and offsets
  const scale = Math.max(containerWidth / naturalWidth, containerHeight / naturalHeight);
  const offsetX = (containerWidth - (naturalWidth * scale)) / 2;
  const offsetY = (containerHeight - (naturalHeight * scale)) / 2;

  const x = bbox.x * scale + offsetX;
  const y = bbox.y * scale + offsetY;
  const w = bbox.w * scale;
  const h = bbox.h * scale;

  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const color = isError ? '#dc3545' : '#00ff0dff';
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.strokeRect(x, y, w, h);
}

function clearCanvas() {
  const canvas = $('bboxCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}


// ═══════════════════════════════════════════════════════════
//  WEBSOCKET FOR AUTO-CAPTURE
// ═══════════════════════════════════════════════════════════

function startWS() {
  if (ws) return;
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log('[WS] Connected for registration');
  };

  ws.onmessage = (e) => {
    if (isSubmitting || isAutoCapturing) return;
    try {
      const data = JSON.parse(e.data);
      if (data.event === 'live_faces') {
        handleLiveFaces(data.faces);
      }
    } catch (err) {
      console.warn('[WS] Error parsing message:', err);
    }
  };

  ws.onclose = () => {
    ws = null;
    if (captureScreen.style.display === 'block') {
      setTimeout(startWS, 2000);
    }
  };
}

function stopWS() {
  if (ws) {
    ws.close();
    ws = null;
  }
  const guide = $('faceGuide');
  const line = $('scannerLine');
  if (guide) {
    guide.classList.remove('scanning');
    guide.classList.remove('warning');
  }
  if (line) {
    line.classList.remove('active');
  }
}

function handleLiveFaces(faces) {
  if (!faces || faces.length === 0) {
    detectStartTime = null;
    clearCanvas();
    updateProgress(0, 'Đang tìm khuôn mặt...');
    return;
  }

  const img = $('camImg');
  if (!img || !img.naturalWidth) return;

  // Calculate center of the camera frame
  const frameWidth = img.naturalWidth || 640;
  const frameHeight = img.naturalHeight || 480;
  const centerX = frameWidth / 2;
  const centerY = frameHeight / 2;

  // Map and calculate distance of each face's center to the frame center
  const facesWithDistance = faces.map(f => {
    if (!f.bbox) return null;
    const faceCenterX = f.bbox.x + f.bbox.w / 2;
    const faceCenterY = f.bbox.y + f.bbox.h / 2;
    const dist = Math.sqrt(Math.pow(faceCenterX - centerX, 2) + Math.pow(faceCenterY - centerY, 2));
    return { face: f, dist: dist };
  }).filter(item => item !== null);

  if (facesWithDistance.length === 0) {
    detectStartTime = null;
    clearCanvas();
    updateProgress(0, 'Đang tìm khuôn mặt...');
    return;
  }

  // Sort by distance ascending (closest to center first)
  facesWithDistance.sort((a, b) => a.dist - b.dist);

  // Pick the most central face as the target
  const targetFace = facesWithDistance[0].face;

  // Check duplicate face in database (if user_code matched)
  if (targetFace.name && targetFace.name !== 'Unknown') {
    detectStartTime = null;
    if (targetFace.bbox) drawTargetBox(targetFace.bbox, true); // Red box
    updateProgress(0, 'Khuôn mặt đã được đăng ký', true);
    return;
  }

  // Draw green targeting box on the closest face
  if (targetFace.bbox) drawTargetBox(targetFace.bbox, false);

  if (detectStartTime) {
    const elapsed = Date.now() - detectStartTime;
    const remainingMs = CAPTURE_COOLDOWN - elapsed;
    const remainingSec = Math.ceil(remainingMs / 1000);

    if (remainingMs <= 0) {
      updateProgress(100, 'ĐÃ KHỚP! ĐANG CHỤP...');
      triggerAutoCapture();
    } else {
      updateProgress(0, `Chụp ảnh trong ${remainingSec}...`);
    }
  } else {
    detectStartTime = Date.now();
    updateProgress(0, 'Chụp ảnh trong 3...');
  }
}

function updateProgress(pct, message, isError = false) {
  const text = $('scanStatusText');
  if (text) {
    text.textContent = message;
    if (isError) {
      text.style.color = '#ef4444'; // Error Red color
    } else {
      text.style.color = '#666'; // Default color
    }
  }
}

function triggerAutoCapture() {
  if (isAutoCapturing) return;
  isAutoCapturing = true;

  // Flash shutter effect
  const flash = document.createElement('div');
  flash.style.position = 'absolute';
  flash.style.inset = '0';
  flash.style.background = '#ffffff';
  flash.style.zIndex = '99';
  flash.style.opacity = '1';
  flash.style.transition = 'opacity 0.4s ease-out';

  const box = document.querySelector('.camera-box');
  if (box) {
    box.appendChild(flash);
    setTimeout(() => {
      flash.style.opacity = '0';
      setTimeout(() => flash.remove(), 400);
    }, 50);
  }

  const img = $('camImg');
  if (!img || !img.naturalWidth) {
    isAutoCapturing = false;
    detectStartTime = null;
    return;
  }

  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

  canvas.toBlob((blob) => {
    if (!blob) {
      isAutoCapturing = false;
      detectStartTime = null;
      return;
    }

    capturedBlobs.straight = blob;
    isSubmitting = true;
    stopWS();
    submitRegistration();
  }, 'image/jpeg', 0.95);
}


// ── Realtime duplicate code validation ──
function debounce(func, delay) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => func.apply(this, args), delay);
  };
}

const regUserCodeInput = $('regUserCode');
const regUserCodeError = $('regUserCodeError');

regUserCodeInput?.addEventListener('input', debounce(async () => {
  const userCode = regUserCodeInput.value.trim();
  const submitBtn = kioskRegisterForm?.querySelector('button[type="submit"]');
  if (!userCode) {
    if (regUserCodeError) regUserCodeError.style.display = 'none';
    if (submitBtn) submitBtn.disabled = false;
    return;
  }
  try {
    const checkRes = await fetch(`/api/users/check/${encodeURIComponent(userCode)}`);
    if (checkRes.ok) {
      const checkData = await checkRes.json();
      if (checkData.exists) {
        if (regUserCodeError) {
          regUserCodeError.textContent = 'Mã nhân viên đã tồn tại!';
          regUserCodeError.style.display = 'block';
        }
        if (submitBtn) submitBtn.disabled = true;
      } else {
        if (regUserCodeError) regUserCodeError.style.display = 'none';
        if (submitBtn) submitBtn.disabled = false;
      }
    }
  } catch (error) {
    console.error("Lỗi kiểm tra ID:", error);
  }
}, 300));


// ═══════════════════════════════════════════════════════════
//  TRANSITIONS
// ═══════════════════════════════════════════════════════════

kioskRegisterForm?.addEventListener('submit', async (e) => {
  e.preventDefault();

  const userCode = $('regUserCode').value.trim();
  const fullName = $('regFullName').value.trim();
  const department = $('regDepartment').value;

  if (!userCode || !fullName) {
    Swal.fire({
      title: 'Thiếu thông tin',
      text: 'Vui lòng điền đầy đủ Mã nhân viên và Họ tên.',
      icon: 'warning',
      confirmButtonText: 'Đóng'
    });
    return;
  }

  const submitBtn = kioskRegisterForm.querySelector('button[type="submit"]');
  const originalBtnText = submitBtn ? submitBtn.textContent : 'ĐĂNG KÝ KHUÔN MẶT';
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'ĐANG KIỂM TRA ID...';
  }

  try {
    const checkRes = await fetch(`/api/users/check/${encodeURIComponent(userCode)}`);
    if (checkRes.ok) {
      const checkData = await checkRes.json();
      if (checkData.exists) {
        Swal.fire({
          title: 'Mã nhân viên đã tồn tại',
          text: `Mã nhân viên "${userCode}" đã được đăng ký trong hệ thống.`,
          icon: 'error',
          confirmButtonText: 'Đóng'
        });
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = originalBtnText;
        }
        return;
      }
    }
  } catch (error) {
    console.error("Lỗi kiểm tra ID:", error);
  }

  if (submitBtn) {
    submitBtn.disabled = false;
    submitBtn.textContent = originalBtnText;
  }

  regData.userCode = userCode;
  regData.fullName = fullName;
  regData.department = department;

  formScreen.style.display = 'none';
  captureScreen.style.display = 'block';
  successScreen.style.display = 'none';
  processingScreen.style.display = 'none';
  mainContainer.classList.remove('success-state');

  cameraWaiting.classList.remove('hidden');
  camImg.src = '/api/camera/stream';
  camImg.onload = () => {
    cameraWaiting.classList.add('hidden');
  };

  resetCaptureSteps();
  startWS();
});

function resetCaptureSteps() {
  capturedBlobs = { straight: null, left: null, right: null };
  detectStartTime = null;
  isAutoCapturing = false;
  isSubmitting = false;

  const guide = $('faceGuide');
  const line = $('scannerLine');
  if (guide) {
    guide.classList.remove('scanning');
    guide.classList.remove('warning');
  }
  if (line) {
    line.classList.remove('active');
  }

  if (cameraInstruction) {
    cameraInstruction.innerHTML = 'Nhìn thẳng vào camera và giữ nguyên khuôn mặt';
  }

  updateProgress(0, 'Đang tìm khuôn mặt...');
}

// ═══════════════════════════════════════════════════════════
//  API SUBMISSION
// ═══════════════════════════════════════════════════════════

async function submitRegistration() {
  const startTime = Date.now();

  // Switch to inline processing screen instead of using popup
  formScreen.style.display = 'none';
  captureScreen.style.display = 'none';
  successScreen.style.display = 'none';
  processingScreen.style.display = 'block';

  camImg.src = '';

  try {
    // 1. Post user details
    const resUser = await fetch('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_code: regData.userCode,
        full_name: regData.fullName,
        department: regData.department
      })
    });

    if (!resUser.ok) {
      const errData = await resUser.json().catch(() => ({}));
      throw new Error(errData.detail || `Lỗi tạo tài khoản (Mã lỗi ${resUser.status})`);
    }

    const user = await resUser.json();
    const userId = user.id;

    // 2. Upload single straight photo to Enrollment API
    const blob = capturedBlobs.straight;
    if (!blob) {
      throw new Error('Lỗi: Chưa chụp được ảnh khuôn mặt.');
    }

    const formData = new FormData();
    formData.append('image', blob, `${regData.userCode}_straight.jpg`);

    const resEnroll = await fetch(`/api/enrollments/${userId}`, {
      method: 'POST',
      body: formData
    });

    if (!resEnroll.ok) {
      const errData = await resEnroll.json().catch(() => ({}));
      // Rollback newly created user on failure
      await fetch(`/api/users/${userId}`, { method: 'DELETE' });
      throw new Error(errData.detail || 'Không nhận dạng được khuôn mặt từ ảnh chụp. Hãy thử lại dưới điều kiện ánh sáng tốt hơn.');
    }

    // Ensure loader shows for at least 1.0 second for a premium feel
    const elapsed = Date.now() - startTime;
    const remaining = 1000 - elapsed;
    if (remaining > 0) {
      await new Promise(resolve => setTimeout(resolve, remaining));
    }

    processingScreen.style.display = 'none';
    showSuccessScreen();

  } catch (error) {
    const elapsed = Date.now() - startTime;
    const remaining = 1000 - elapsed;
    if (remaining > 0) {
      await new Promise(resolve => setTimeout(resolve, remaining));
    }

    processingScreen.style.display = 'none';

    Swal.fire({
      title: 'Đăng ký thất bại',
      text: error.message || 'Có lỗi xảy ra trong quá trình truyền dữ liệu.',
      icon: 'error',
      confirmButtonText: 'Đóng'
    }).then(() => {
      resetCaptureSteps();
      captureScreen.style.display = 'block';
      camImg.src = '/api/camera/stream';
      startWS();
    });
  }
}

function showSuccessScreen() {
  captureScreen.style.display = 'none';
  processingScreen.style.display = 'none';
  successScreen.style.display = 'block';
  mainContainer.classList.add('success-state');

  if (capturedBlobs.straight) {
    $('imgStraight').src = URL.createObjectURL(capturedBlobs.straight);
  }

  $('valUserCode').textContent = regData.userCode;
  $('valFullName').textContent = regData.fullName;
  $('valDept').textContent = regData.department;

  const now = new Date();
  const dateStr = now.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }) +
    ' ' +
    now.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  $('valDate').textContent = dateStr;
}

// ═══════════════════════════════════════════════════════════
//  DONE ACTION
// ═══════════════════════════════════════════════════════════

btnDoneReg?.addEventListener('click', () => {
  stopWS();

  $('regUserCode').value = '';
  $('regFullName').value = '';
  $('regDepartment').value = 'Cyber Security';

  $('imgStraight').src = '';

  const errorEl = $('regUserCodeError');
  if (errorEl) errorEl.style.display = 'none';
  const submitBtn = kioskRegisterForm?.querySelector('button[type="submit"]');
  if (submitBtn) submitBtn.disabled = false;

  successScreen.style.display = 'none';
  processingScreen.style.display = 'none';
  formScreen.style.display = 'block';
  mainContainer.classList.remove('success-state');
});
