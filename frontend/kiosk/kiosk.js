/**
 * kiosk.js — AttendAI Kiosk · Clean Production
 * 
 * Chỉ 2 việc: Hiển thị camera + Nhận sự kiện điểm danh qua WebSocket.
 * Không có nút bật/tắt camera — mọi điều khiển từ Admin Panel.
 */

const WS_URL = `ws://${location.host}/ws/attendance`;

let ws = null;
let checkinCount = 0;
let dropTimer = null;
let _checkedUsers = new Set(); // Bộ nhớ tạm để chặn trùng lặp trong phiên hiện tại

// ─── Bbox State ───────────────────────────────────────────
let _currentBoxes = [];
let _boxExpireAt = 0;
let _resultUntil = 0; // Thời điểm hết hạn hiển thị kết quả (Xanh/Đỏ)
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
  // Drop card
  dropCard: $('dropCard'),
  dropAvatar: $('dropAvatar'),
  dropFallback: $('dropAvatarFallback'),
  dropName: $('dropName'),
  dropCode: $('dropCode'),
  dropTime: $('dropTime'),
  dropConfFill: $('dropConfFill'),
  dropConfTxt: $('dropConfTxt'),
  dropStatus: $('dropStatus'),
  // List
  attCount: $('attCount'),
  attList: $('attList'),
  attEmpty: $('attEmpty'),
  // Session
  sessionInfo: $('sessionInfo'),
  sessionLabel: $('sessionLabel'),
  sessionPill: $('sessionPill'),
  // Toast
  toast: $('toast'),
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
      // Chặn trùng lặp: Nếu đã điểm danh trong phiên này rồi thì không hiện drop-card nữa
      if (_checkedUsers.has(data.user_id)) {
        // Chỉ cập nhật khung xanh để biết vẫn nhận diện được, không chạy animation drop-card
        setBoxes([{
          bbox: data.bbox,
          label: `✓ ${data.full_name}`,
          color: '#22c55e',
        }], true);
        break;
      }

      _checkedUsers.add(data.user_id);
      setBoxes([{
        bbox: data.bbox,
        label: `✓ ${data.full_name}  ${Math.round(data.confidence * 100)}%`,
        color: '#22c55e',
      }], true);
      showDropCard(data);
      addCheckinItem(data);
      showToast(`✅ ${data.full_name} — Điểm danh thành công`, 'success');
      break;

    // ── Đã điểm danh rồi ──
    case 'already_checked_in':
      setBoxes([{
        bbox: data.bbox,
        label: `${data.full_name} ✓ Đã có mặt`,
        color: '#22c55e',
      }], true);
      break;

    // ── Khuôn mặt lạ ──
    case 'unknown_face':
      setBoxes([{
        bbox: data.bbox,
        label: 'Không nhận ra',
        color: '#ef4444',
      }], true);
      break;

    // ── Frame stats ──
    case 'frame_stats':
      DOM.hudFaces.textContent = `👤 ${data.faces_detected} khuôn mặt`;
      DOM.hudFps.textContent = `${data.fps} FPS`;
      // Hide waiting overlay when frames are coming
      if (!DOM.camWaiting.classList.contains('hidden')) {
        DOM.camWaiting.classList.add('hidden');
      }
      break;

    // ── Camera offline ──
    case 'camera_offline':
      DOM.camWaiting.classList.remove('hidden');
      _currentBoxes = [];
      break;

    case 'live_faces':
      if (Date.now() < _resultUntil) break;
      if (data.faces && data.faces.length > 0) {
        setBoxes(data.faces.map(f => {
          let color = '#ffffff'; // Mặc định Trắng
          if (f.name === 'Unknown') color = '#ef4444'; // Đỏ
          else if (f.name) color = '#22c55e'; // Xanh lá
          
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
//  DROP-FACE CARD (Success Animation)
// ═══════════════════════════════════════════════════════════

function showDropCard(data, isAgain = false) {
  // Clear previous timer
  if (dropTimer) clearTimeout(dropTimer);

  // Set data
  DOM.dropName.textContent = data.full_name || '—';
  DOM.dropCode.textContent = data.user_code || data.student_code || '—';

  const timeStr = data.check_in_time || data.checkin_time || new Date().toISOString();
  const time = new Date(timeStr).toLocaleTimeString('vi-VN', { hour12: false });
  DOM.dropTime.textContent = time;

  const confPct = Math.round((data.confidence || 0) * 100);
  DOM.dropConfFill.style.width = confPct + '%';
  DOM.dropConfTxt.textContent = confPct + '%';

  // Avatar
  const snap = data.snapshot_path
    ? `/storage/snapshots/${data.snapshot_path.split(/[/\\]/).pop()}`
    : '';
  
  if (snap) {
    DOM.dropAvatar.src = snap;
    DOM.dropAvatar.style.display = 'block';
  } else {
    DOM.dropAvatar.style.display = 'none';
  }

  // Status
  DOM.dropStatus.textContent = isAgain ? '✓ Bạn đã điểm danh rồi' : '✅ Điểm danh thành công';

  // Force re-trigger CSS animation by re-creating inner HTML for SVG
  const svgWrap = DOM.dropCard.querySelector('.drop-check');
  if (svgWrap) {
    svgWrap.innerHTML = `
      <svg viewBox="0 0 52 52" class="drop-check-svg">
        <circle cx="26" cy="26" r="25" fill="none" stroke="currentColor" stroke-width="2"/>
        <path fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
      </svg>`;
  }

  // Show card with animation
  DOM.dropCard.classList.add('visible');

  // Auto-hide after 6 seconds
  dropTimer = setTimeout(() => {
    DOM.dropCard.classList.remove('visible');
  }, 6000);
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

  const confPct = Math.round((data.confidence || 0) * 100);

  // Avatar xử lý từ storage
  let avatarSrc = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(data.full_name) + '&background=random';
  if (data.snapshot_path) {
    avatarSrc = `/storage/snapshots/${data.snapshot_path.split(/[/\\]/).pop()}`;
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
      <div class="att-conf">${confPct}%</div>
    </div>
  `;

  DOM.attList.prepend(item);
}


// ═══════════════════════════════════════════════════════════
//  BOUNDING BOX (Canvas)
// ═══════════════════════════════════════════════════════════

function setBoxes(boxes, isResult = false) {
  if (isResult) {
    _resultUntil = Date.now() + 1500; // Giữ màu kết quả trong 1.5 giây
  } else {
    // Nếu đang hiện kết quả, không nhận khung live
    if (Date.now() < _resultUntil) return;
  }
  _currentBoxes = boxes;
  _boxExpireAt = Date.now() + (isResult ? 2000 : BOX_TTL);
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
  const scaleX = canvas.width / (img.naturalWidth || 640);
  const scaleY = canvas.height / (img.naturalHeight || 480);

  for (const { bbox, label, color } of _currentBoxes) {
    if (!bbox) continue;
    const x = bbox.x * scaleX;
    const y = bbox.y * scaleY;
    const w = bbox.w * scaleX;
    const h = bbox.h * scaleY;

    // Glow
    ctx.shadowColor = color;
    ctx.shadowBlur = 14;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);

    // Corner marks
    ctx.lineWidth = 3;
    const cs = Math.min(w, h) * 0.18;
    [[x, y], [x + w, y], [x, y + h], [x + w, y + h]].forEach(([cx, cy], i) => {
      ctx.beginPath();
      const sx = (i % 2 === 0) ? cs : -cs;
      const sy = (i < 2) ? cs : -cs;
      ctx.moveTo(cx + sx, cy);
      ctx.lineTo(cx, cy);
      ctx.lineTo(cx, cy + sy);
      ctx.stroke();
    });

    // Label
    ctx.shadowBlur = 0;
    ctx.font = 'bold 13px Inter, sans-serif';
    const tw = ctx.measureText(label).width;
    const ly = y > 30 ? y - 30 : y + h + 4;

    roundRect(ctx, x, ly, tw + 16, 24, 5);
    ctx.fillStyle = color + 'dd';
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
      DOM.sessionInfo.textContent = `${s.class_name || ''} · ${s.session_code}`;
      DOM.sessionLabel.textContent = s.class_name || s.session_code;
      DOM.sessionPill.style.display = 'flex';
      loadAttendanceHistory(s.id); // Tải lịch sử khi có session
    } else {
      DOM.sessionInfo.textContent = 'Chờ phiên học mới...';
      DOM.sessionLabel.textContent = '—';
      _checkedUsers.clear(); 
    }
  } catch {}
}


// ═══════════════════════════════════════════════════════════
//  TOAST
// ═══════════════════════════════════════════════════════════

let toastTimer;
function showToast(msg, type = '') {
  DOM.toast.textContent = msg;
  DOM.toast.className = `toast show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    DOM.toast.className = 'toast';
  }, 3500);
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
  } catch(e) { console.error("History error:", e); }
}
