/**
 * kiosk.js — AttendAI Kiosk · Clean Production
 * 
 * Chỉ 2 việc: Hiển thị camera + Nhận sự kiện điểm danh qua WebSocket.
 * Không có nút bật/tắt camera — mọi điều khiển từ Admin Panel.
 */

const WS_URL = `ws://${location.host}/ws/attendance`;

let ws = null;
let checkinCount = 0;
let _checkedUsers = new Set(); // Bộ nhớ tạm để chặn trùng lặp trong phiên hiện tại

// ─── Bbox State ───────────────────────────────────────────
let _currentBoxes = [];
let _boxExpireAt = 0;
const BOX_TTL = 1800;

// ─── DOM Cache ────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const DOM = {
  clock: $('clock'),
  camImg: $('camImg'),
  camWaiting: $('camWaiting'),
  camHud: $('camHud'),
  hudFaces: $('hudFaces'),
  hudFps: $('hudFps'),
  // List
  attCount: $('attCount'),
  attList: $('attList'),
  attEmpty: $('attEmpty'),
  // Session
  sessionInfo: $('sessionInfo'),
  sessionLabel: $('sessionLabel'),
  sessionPill: $('sessionPill'),
};


// ═══════════════════════════════════════════════════════════
//  CLOCK
// ═══════════════════════════════════════════════════════════

function updateClock() {
  DOM.clock.textContent = new Date().toLocaleTimeString('vi-VN', { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();


// ═══════════════════════════════════════════════════════════
//  WEBSOCKET
// ═══════════════════════════════════════════════════════════

function connectWS() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log('[WS] Connected');
  };

  ws.onmessage = (e) => {
    try {
      handleEvent(JSON.parse(e.data));
    } catch (err) {
      console.warn('[WS] Parse error:', err);
    }
  };

  ws.onclose = () => {
    console.log('[WS] Disconnected');
    setTimeout(connectWS, 3000);
  };

  ws.onerror = () => {
    console.warn('[WS] Error');
  };
}


// ═══════════════════════════════════════════════════════════
//  EVENT HANDLER
// ═══════════════════════════════════════════════════════════

function handleEvent(data) {
  switch (data.event) {

    // ── Điểm danh thành công ──
    case 'checkin_success':
      if (!_checkedUsers.has(data.user_id)) {
        _checkedUsers.add(data.user_id);
        addCheckinItem(data);
      }
      break;

    // ── Đã điểm danh rồi ──
    case 'already_checked_in':
      // Nếu chưa có trong danh sách hiển thị bên phải, hãy thêm vào
      if (!_checkedUsers.has(data.user_id)) {
        _checkedUsers.add(data.user_id);
        if (!data.checkin_time) {
          data.checkin_time = new Date().toISOString();
        }
        addCheckinItem(data);
      }
      break;

    // ── Khuôn mặt lạ ──
    case 'unknown_face':
      break;

    // ── Frame stats ──
    case 'frame_stats':
      if (DOM.hudFaces) DOM.hudFaces.textContent = `👤 ${data.faces_detected} khuôn mặt`;
      if (DOM.hudFps) DOM.hudFps.textContent = `${data.fps} FPS`;
      // Hide waiting overlay when frames are coming
      if (DOM.camWaiting && !DOM.camWaiting.classList.contains('hidden')) {
        DOM.camWaiting.classList.add('hidden');
      }
      break;

    // ── Camera offline ──
    case 'camera_offline':
      DOM.camWaiting.classList.remove('hidden');
      _currentBoxes = [];
      break;

    case 'live_faces':
      if (data.faces && data.faces.length > 0) {
        setBoxes(data.faces.map(f => {
          let color = '#ffffff'; // Mặc định Trắng
          if (f.name === 'Unknown') color = '#dc3545'; // Đỏ
          else if (f.name) color = '#13ca75'; // Xanh lá

          return {
            bbox: f.bbox,
            label: f.name || '',
            color: color
          };
        }));
      } else {
        _currentBoxes = [];
      }
      break;

    case 'session_start':
    case 'session_stop':
      _checkedUsers.clear(); // Reset chặn trùng lặp khi đổi phiên
      loadSession();
      break;
  }
}



// ═══════════════════════════════════════════════════════════
//  CHECK-IN LIST
// ═══════════════════════════════════════════════════════════

function addCheckinItem(data) {
  // Ẩn thông báo trống
  const empty = document.getElementById('attEmpty');
  if (empty) empty.style.display = 'none';

  checkinCount++;
  DOM.attCount.textContent = checkinCount;

  // Hỗ trợ cả check_in_time (DB) và checkin_time (Live event)
  const timeStr = data.check_in_time || data.checkin_time || new Date().toISOString();
  const time = new Date(timeStr).toLocaleTimeString('vi-VN', { hour12: false });

  // Avatar xử lý từ storage
  let avatarSrc = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(data.full_name) + '&background=random';
  if (data.snapshot_path) {
    avatarSrc = `/storage/snapshots/${data.snapshot_path.split(/[/\\]/).pop()}`;
  } else if (data.face_image) {
    avatarSrc = `/storage/enrolled/${data.face_image.split(/[/\\]/).pop()}`;
  }

  const item = document.createElement('div');
  item.className = 'att-item';
  item.innerHTML = `
    <img class="att-avatar" src="${avatarSrc}" onerror="this.src='https://ui-avatars.com/api/?name=${encodeURIComponent(data.full_name)}&background=random'"/>
    <div class="att-info">
      <div class="att-name">${esc(data.full_name)}</div>
      <div class="att-code">${esc(data.user_code || data.student_code || '—')}</div>
    </div>
    <div class="att-meta">
      <div class="att-time">${time}</div>
    </div>
  `;

  DOM.attList.prepend(item);
}


// ═══════════════════════════════════════════════════════════
//  BOUNDING BOX (Canvas)
// ═══════════════════════════════════════════════════════════

function setBoxes(boxes) {
  _currentBoxes = boxes;
  _boxExpireAt = Date.now() + BOX_TTL;
}

const canvas = $('bboxCanvas');
const ctx = canvas.getContext('2d');

function resizeCanvas() {
  const img = DOM.camImg;
  canvas.width = img.clientWidth;
  canvas.height = img.clientHeight;
}

function drawLoop() {
  resizeCanvas();
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (Date.now() > _boxExpireAt) {
    _currentBoxes = [];
  }

  if (_currentBoxes.length === 0) {
    requestAnimationFrame(drawLoop);
    return;
  }

  const img = DOM.camImg;
  const containerWidth = canvas.width;
  const containerHeight = canvas.height;
  const naturalWidth = img.naturalWidth || 1280;
  const naturalHeight = img.naturalHeight || 720;

  // Calculate cover scaling factors and offsets
  const scale = Math.max(containerWidth / naturalWidth, containerHeight / naturalHeight);
  const offsetX = (containerWidth - (naturalWidth * scale)) / 2;
  const offsetY = (containerHeight - (naturalHeight * scale)) / 2;

  for (const { bbox, label, color } of _currentBoxes) {
    if (!bbox) continue;
    const x = bbox.x * scale + offsetX;
    const y = bbox.y * scale + offsetY;
    const w = bbox.w * scale;
    const h = bbox.h * scale;

    // Box — solid, no glow
    ctx.shadowBlur = 0;
    ctx.shadowColor = 'transparent';
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);



    // Label — solid background
    ctx.font = 'bold 13px Inter, sans-serif';
    const tw = ctx.measureText(label).width;
    const ly = y > 30 ? y - 30 : y + h + 4;

    roundRect(ctx, x, ly, tw + 16, 24, 5);
    ctx.fillStyle = color;
    ctx.fill();

    ctx.fillStyle = '#fff';
    ctx.fillText(label, x + 8, ly + 16);
  }

  requestAnimationFrame(drawLoop);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

requestAnimationFrame(drawLoop);


// ═══════════════════════════════════════════════════════════
//  SESSION INFO
// ═══════════════════════════════════════════════════════════

async function loadSession() {
  try {
    const r = await fetch('/api/sessions/active');
    if (!r.ok) return;
    const s = await r.json();
    if (s && s.session_code) {
      if (DOM.sessionInfo) DOM.sessionInfo.textContent = `${s.class_name || ''} · ${s.session_code}`;
      if (DOM.sessionLabel) DOM.sessionLabel.textContent = s.class_name || s.session_code;
      if (DOM.sessionPill) DOM.sessionPill.style.display = 'flex';
      loadAttendanceHistory(s.id); // Tải lịch sử khi có session
    } else {
      if (DOM.sessionInfo) DOM.sessionInfo.textContent = 'Chờ phiên học mới...';
      if (DOM.sessionLabel) DOM.sessionLabel.textContent = '—';
      _checkedUsers.clear();
    }
  } catch { }
}




// ═══════════════════════════════════════════════════════════
//  UTILS
// ═══════════════════════════════════════════════════════════

function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}


// ═══════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════

// Camera stream — auto-load (controlled from Admin)
DOM.camImg.src = `/api/camera/stream?t=${Date.now()}`;

// Start WebSocket
connectWS();

// Load session info
loadSession();
setInterval(loadSession, 30000);

// Detect camera online via image load
DOM.camImg.onload = () => {
  if (!DOM.camWaiting.classList.contains('hidden')) {
    DOM.camWaiting.classList.add('hidden');
  }
};

DOM.camImg.onerror = () => {
  DOM.camWaiting.classList.remove('hidden');
};

async function loadAttendanceHistory(sessionId) {
  try {
    const r = await fetch(`/api/attendance/logs?session_id=${sessionId}&limit=100`);
    const d = await r.json();
    DOM.attList.innerHTML = '';
    _checkedUsers.clear();
    checkinCount = 0;

    if (d.logs && d.logs.length > 0) {
      // Đảo ngược để prepend vào đúng thứ tự (người mới nhất lên đầu)
      const logs = [...d.logs].reverse();
      logs.forEach(log => {
        _checkedUsers.add(log.user_id);
        addCheckinItem(log);
      });
    } else {
      DOM.attList.innerHTML = '<div class="att-empty" id="attEmpty">Chưa có ai điểm danh</div>';
    }
  } catch (e) { console.error("History error:", e); }
}

// ═══════════════════════════════════════════════════════════
//  END OF KIOSK CLIENT
// ═══════════════════════════════════════════════════════════


