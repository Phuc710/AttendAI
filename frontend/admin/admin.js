const API_BASE = "";

const state = {
  users: [],
  attendance: [],
  systemLogs: [],
  ws: null,
  reconnectTimer: null
};

const viewMeta = {
  dashboard: ["Phân tích biểu đồ", "Phân tích tần suất và lưu lượng điểm danh nhân viên"],
  attendance: ["Nhật ký điểm danh", "Tra cứu log điểm danh và xuất báo cáo"],
  users: ["Đăng ký nhân sự", "Quản lý mã nhân viên, phòng ban và Face ID"],
  "system-logs": ["Nhật ký hệ thống", "Tra cứu lịch sử hoạt động và sự kiện hệ thống"],
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

document.addEventListener("DOMContentLoaded", init);

// ─── AUTHENTICATION CHECK ─────────────────────────────────
function checkAuth() {
  const overlay = $("#adminLoginOverlay");
  const isAuthenticated = sessionStorage.getItem("admin_authenticated") === "true";
  
  if (isAuthenticated) {
    overlay.classList.add("hidden");
  } else {
    overlay.classList.remove("hidden");
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const password = $("#adminPasswordInput").value;
  try {
    await request("/api/auth/login", jsonOptions("POST", { password }));
    sessionStorage.setItem("admin_authenticated", "true");
    $("#adminLoginOverlay").classList.add("hidden");
    showToast("Đăng nhập thành công!");
    refreshAll();
  } catch (error) {
    showToast(error.message || "Mật khẩu không chính xác!", true);
  }
}

function handleLogout() {
  sessionStorage.removeItem("admin_authenticated");
  location.reload();
}

// ─── INITIALIZATION ───────────────────────────────────────
function init() {
  checkAuth();
  
  // Auth Form
  $("#adminLoginForm")?.addEventListener("submit", handleLogin);
  $("#logoutBtn")?.addEventListener("click", handleLogout);

  bindUi();
  startClock();
  connectWebSocket();
  
  if (sessionStorage.getItem("admin_authenticated") === "true") {
    refreshAll();
  }
}

function bindUi() {
  document.addEventListener("click", handleDocumentClick);

  $("#userEditForm")?.addEventListener("submit", handleEditUser);

  $("#userRoleFilter")?.addEventListener("change", renderUsers);
  $("#userDateFilter")?.addEventListener("change", renderUsers);
  $("#userSearchFilter")?.addEventListener("input", debounce(renderUsers, 250));

  $("#attendanceDeptFilter")?.addEventListener("change", loadAttendance);
  $("#attendanceDateFilter")?.addEventListener("change", loadAttendance);
  $("#attendanceSearchFilter")?.addEventListener("input", debounce(loadAttendance, 250));

  $("#syslogTypeFilter")?.addEventListener("change", loadSystemLogs);
  $("#syslogDateFilter")?.addEventListener("change", loadSystemLogs);
  $("#syslogSearchFilter")?.addEventListener("input", debounce(loadSystemLogs, 250));

  const preview = $("#cameraPreview");
  const waiting = $("#adminCamWaiting");
  if (preview && waiting) {
    preview.addEventListener("load", () => {
      waiting.classList.add("hidden");
    });
    preview.addEventListener("error", () => {
      waiting.classList.remove("hidden");
    });
  }
}

function handleDocumentClick(event) {
  const viewButton = event.target.closest("[data-view]");
  if (viewButton) {
    event.preventDefault();
    showView(viewButton.dataset.view);
    return;
  }

  const actionButton = event.target.closest("[data-action]");
  if (!actionButton) return;

  event.preventDefault();
  dispatchAction(actionButton.dataset.action, actionButton);
}

function dispatchAction(action, button) {
  const id = Number(button.dataset.id || 0);
  const actions = {
    "refresh-all": refreshAll,
    "start-camera": startCamera,
    "stop-camera": stopCamera,
    "clear-attendance-filter": clearAttendanceFilter,
    "clear-syslog-filter": clearSyslogFilter,
    "export-attendance": exportAttendance,
    "edit-user": () => openUserDialog(id),
    "delete-user": () => deleteUser(id),
    "close-user-dialog": closeUserDialog,
  };

  const handler = actions[action];
  if (handler) handler();
}

function showView(view) {
  if (!viewMeta[view]) return;

  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === view));
  $$(".view-panel").forEach(panel => panel.classList.toggle("active", panel.dataset.panel === view));

  const [title, subtitle] = viewMeta[view];
  $("#pageTitle").textContent = title;
  $("#pageSubtitle").textContent = subtitle;

  if (view === "attendance") loadAttendance();
  if (view === "system-logs") loadSystemLogs();
  if (view === "dashboard") {
    renderCharts();
    updateDashboardMetrics();
  }
}

function startClock() {
  const update = () => {
    const clock = $("#clock");
    if (clock) {
      clock.textContent = new Date().toLocaleTimeString("vi-VN", { hour12: false });
    }
  };
  update();
  setInterval(update, 1000);
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");

  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload.detail : payload;
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return payload;
}

function jsonOptions(method, body) {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

// ─── REFRESH DATA ─────────────────────────────────────────
async function refreshAll() {
  if (sessionStorage.getItem("admin_authenticated") !== "true") return;
  await Promise.allSettled([
    loadUsers(),
    loadAttendance(),
    loadSystemLogs()
  ]);
}

// ─── USERS / STAFF CRUD ───────────────────────────────────
async function loadUsers() {
  try {
    const data = await request("/api/users");
    state.users = data.users || [];
    renderUsers();
    updateDashboardMetrics();
    renderCharts();
  } catch (error) {
    renderTableError("userTableBody", 7, error);
  }
}

function renderUsers() {
  const dept = $("#userRoleFilter")?.value || "";
  const dateVal = $("#userDateFilter")?.value || "";
  const search = $("#userSearchFilter")?.value.trim().toLowerCase() || "";

  let users = state.users;
  if (dept) {
    users = users.filter(user => user.department === dept);
  }
  if (dateVal) {
    users = users.filter(user => checkDateMatch(user.created_at, dateVal));
  }
  if (search) {
    users = users.filter(user => 
      (user.full_name && user.full_name.toLowerCase().includes(search)) || 
      (user.user_code && user.user_code.toLowerCase().includes(search))
    );
  }

  const body = $("#userTableBody");
  if (!body) return;

  $("#userCountText").textContent = `${users.length} bản ghi`;

  if (!users.length) {
    body.innerHTML = `<tr><td colspan="6" class="empty-row">Không có nhân viên phù hợp.</td></tr>`;
    return;
  }

  body.innerHTML = users.map(user => `
    <tr>
      <td>${renderFaceCell(user)}</td>
      <td><code>${escapeText(user.user_code)}</code></td>
      <td><div class="cell-main">${escapeText(user.full_name)}</div></td>
      <td><div class="cell-sub" style="font-weight:600;">${escapeText(user.department || "—")}</div></td>
      <td>${formatDateTime(user.created_at)}</td>
      <td>
        <div class="action-cell">
          <button class="btn btn-secondary" type="button" data-action="edit-user" data-id="${user.id}">Sửa</button>
          <button class="btn btn-danger" type="button" data-action="delete-user" data-id="${user.id}">Xóa</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function renderFaceCell(user) {
  if (user.face_image) {
    const url = `/storage/enrolled/${user.face_image.split(/[/\\]/).pop()}`;
    return `<img class="table-avatar" src="${url}" alt="Avatar" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' viewBox=\\'0 0 24 24\\' fill=\\'%23ccc\\'><circle cx=\\'12\\' cy=\\'8\\' r=\\'4\\'/><path d=\\'M12 14c-6.1 0-8 4-8 4h16s-1.9-4-8-4z\\'/></svg>'">`;
  }
  return `<div class="table-avatar-fallback">👤</div>`;
}



async function openUserDialog(userId) {
  const user = state.users.find(item => item.id === userId) || await request(`/api/users/${userId}`);
  $("#editUserId").value = user.id;
  $("#editUserCode").value = user.user_code || "";
  $("#editUserName").value = user.full_name || "";
  $("#editUserDept").value = user.department || "Cyber Security";
  $("#userEditDialog").showModal();
}

function closeUserDialog() {
  $("#userEditDialog")?.close();
}

async function handleEditUser(event) {
  event.preventDefault();
  const id = Number($("#editUserId").value);
  const submit = event.currentTarget.querySelector("button[type='submit']");
  const body = {
    user_code: $("#editUserCode").value.trim(),
    full_name: $("#editUserName").value.trim(),
    department: $("#editUserDept").value
  };

  setBusy(submit, true, "Đang lưu");
  try {
    await request(`/api/users/${id}`, jsonOptions("PUT", body));
    showToast("Đã cập nhật thông tin nhân viên.");
    closeUserDialog();
    await loadUsers();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(submit, false, "Lưu thay đổi");
  }
}

async function deleteUser(userId) {
  if (!userId) return;

  const result = await Swal.fire({
    title: "Xác nhận xóa?",
    text: "Thông tin nhân sự và dữ liệu của người này sẽ bị xóa khỏi danh sách hệ thống.",
    icon: "warning",
    showCancelButton: true,
    confirmButtonColor: "var(--danger, #c93737)",
    cancelButtonColor: "var(--muted, #687386)",
    confirmButtonText: "Đồng ý xóa",
    cancelButtonText: "Hủy bỏ",
    background: "var(--surface, #ffffff)",
    color: "var(--text, #18212f)"
  });

  if (result.isConfirmed) {
    try {
      await request(`/api/users/${userId}`, { method: "DELETE" });
      Swal.fire({
        title: "Đã xóa!",
        text: "Thông tin nhân sự đã được loại bỏ khỏi hệ thống.",
        icon: "success",
        confirmButtonColor: "var(--primary, #1d66d0)",
        background: "var(--surface, #ffffff)",
        color: "var(--text, #18212f)"
      });
      await refreshAll();
    } catch (error) {
      Swal.fire({
        title: "Lỗi!",
        text: error.message,
        icon: "error",
        confirmButtonColor: "var(--primary, #1d66d0)",
        background: "var(--surface, #ffffff)",
        color: "var(--text, #18212f)"
      });
    }
  }
}

async function enrollFiles(userId, files) {
  const result = { ok: 0, failed: 0, errors: [] };
  const selected = Array.from(files).filter(file => file.type.startsWith("image/")).slice(0, 6);

  for (const file of selected) {
    const form = new FormData();
    form.append("image", file);
    try {
      await request(`/api/enrollments/${userId}`, { method: "POST", body: form });
      result.ok += 1;
    } catch (error) {
      result.failed += 1;
      result.errors.push(`${file.name}: ${error.message}`);
    }
  }
  return result;
}

function showEnrollResult(result, name) {
  if (result.failed === 0) {
    showToast(`${name}: Đã đăng ký thành công ${result.ok} ảnh khuôn mặt.`);
  } else {
    showToast(`${name}: ${result.ok} ảnh thành công, ${result.failed} ảnh lỗi.`, true);
  }
}

// ─── ATTENDANCE LOGS ──────────────────────────────────────
async function loadAttendance() {
  try {
    const dept = $("#attendanceDeptFilter")?.value || "";
    const dateVal = $("#attendanceDateFilter")?.value || "";
    const search = $("#attendanceSearchFilter")?.value.trim().toLowerCase() || "";

    let url = `/api/attendance/logs?limit=300`;
    if (dept) url += `&department=${encodeURIComponent(dept)}`;

    const data = await request(url);
    let logs = data.logs || [];

    if (dateVal) {
      logs = logs.filter(log => checkDateMatch(log.check_in_time, dateVal));
    }

    if (search) {
      logs = logs.filter(log => 
        (log.full_name && log.full_name.toLowerCase().includes(search)) || 
        (log.user_code && log.user_code.toLowerCase().includes(search))
      );
    }

    state.attendance = logs;
    renderAttendance();
    updateDashboardMetrics();
    renderCharts();
  } catch (error) {
    renderTableError("attendanceTableBody", 6, error);
  }
}

function renderAttendance() {
  const body = $("#attendanceTableBody");
  if (!body) return;

  $("#attendanceCountText").textContent = `${state.attendance.length} bản ghi`;

  if (!state.attendance.length) {
    body.innerHTML = `<tr><td colspan="6" class="empty-row">Không tìm thấy bản ghi quét nào.</td></tr>`;
    return;
  }

  body.innerHTML = state.attendance.map(log => `
    <tr>
      <td>${renderLogFaceCell(log)}</td>
      <td><code>${escapeText(log.user_code)}</code></td>
      <td><div class="cell-main">${escapeText(log.full_name)}</div></td>
      <td><span class="cell-sub" style="font-weight:600;">${escapeText(log.department || "—")}</span></td>
      <td>${formatDateTime(log.check_in_time)}</td>
      <td><strong style="color:var(--primary);">${Math.round(log.confidence * 100)}%</strong></td>
    </tr>
  `).join("");
}

function renderLogFaceCell(log) {
  let url = "";
  if (log.snapshot_path) {
    url = `/storage/snapshots/${log.snapshot_path.split(/[/\\]/).pop()}`;
  } else if (log.face_image) {
    url = `/storage/enrolled/${log.face_image.split(/[/\\]/).pop()}`;
  }

  if (url) {
    const fallbackUrl = log.face_image 
      ? `/storage/enrolled/${log.face_image.split(/[/\\]/).pop()}`
      : `data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23ccc'><circle cx='12' cy='8' r='4'/><path d='M12 14c-6.1 0-8 4-8 4h16s-1.9-4-8-4z'/></svg>`;

    return `<img class="table-avatar" src="${url}" alt="Avatar" onerror="if (this.src.indexOf('/storage/enrolled/') === -1) { this.src='${fallbackUrl}'; } else { this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' viewBox=\\'0 0 24 24\\' fill=\\'%23ccc\\'><circle cx=\\'12\\' cy=\\'8\\' r=\\'4\\'/><path d=\\'M12 14c-6.1 0-8 4-8 4h16s-1.9-4-8-4z\\'/></svg>'; }">`;
  }
  return `<div class="table-avatar-fallback">👤</div>`;
}

function clearAttendanceFilter() {
  if ($("#attendanceDeptFilter")) $("#attendanceDeptFilter").value = "";
  if ($("#attendanceDateFilter")) $("#attendanceDateFilter").value = "";
  if ($("#attendanceSearchFilter")) $("#attendanceSearchFilter").value = "";
  loadAttendance();
}

function exportAttendance() {
  if (!state.attendance.length) {
    showToast("Không có dữ liệu để xuất.", true);
    return;
  }
  const headers = ["Mã nhân viên", "Họ và tên", "Phòng ban", "Thời gian quét", "Độ tin cậy"];
  const rows = state.attendance.map(log => [
    log.user_code,
    log.full_name,
    log.department || "",
    log.check_in_time,
    `${Math.round(log.confidence * 100)}%`
  ]);

  const csvContent = "\uFEFF" + [headers.join(","), ...rows.map(e => e.map(val => `"${String(val).replace(/"/g, '""')}"`).join(","))].join("\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.setAttribute("download", `log_diem_danh_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast("Đã tải tệp CSV báo cáo.");
}

// ─── DASHBOARD METRICS & CHARTS ───────────────────────────
function updateDashboardMetrics() {
  // Lấy ngày hôm nay theo local time (tránh lệch múi giờ UTC+7)
  const now = new Date();
  const localToday = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;

  const totalEmployees = state.users.length;

  // Lọc log hôm nay theo local date
  const todayLogs = state.attendance.filter(log => {
    if (!log.check_in_time) return false;
    const d = new Date(log.check_in_time);
    const logDate = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    return logDate === localToday;
  });

  // Đã đi làm hôm nay (số nhân viên độc nhất check-in hôm nay)
  const uniqueUsersToday = new Set(todayLogs.map(log => log.user_code)).size;

  // Lượt quét hôm nay (tổng bản ghi check-in ngày hôm nay)
  const scansToday = todayLogs.length;

  // Tổng tất cả lượt quét (toàn bộ lịch sử)
  const totalScans = state.attendance.length;

  // Cập nhật lên UI
  if ($("#metricStudents"))      $("#metricStudents").textContent      = totalEmployees;
  if ($("#metricActiveSession")) $("#metricActiveSession").textContent = uniqueUsersToday;
  if ($("#metricClasses"))       $("#metricClasses").textContent       = scansToday;
  if ($("#metricAttendance"))    $("#metricAttendance").textContent    = totalScans;
}

function renderCharts() {
  const deptContainer = $("#deptChartContainer");
  const weeklyContainer = $("#weeklyChart");
  
  if (deptContainer) {
    // Thống kê phòng ban hôm nay
    const now = new Date();
    const todayStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
    const todayLogs = state.attendance.filter(log => checkDateMatch(log.check_in_time, todayStr));
    
    const depts = {
      "Cyber Security": 0,
      "Physical Intelligence": 0,
      "Logistics & Supply": 0,
      "Executive Board": 0
    };
    
    todayLogs.forEach(log => {
      const d = log.department || "Cyber Security";
      if (depts[d] !== undefined) depts[d]++;
    });
    
    const maxVal = Math.max(...Object.values(depts), 1);
    
    deptContainer.innerHTML = Object.entries(depts).map(([dept, val]) => {
      const pct = Math.round((val / maxVal) * 100);
      return `
        <div class="chart-bar-row">
          <div class="chart-bar-label">${dept}</div>
          <div class="chart-bar-track">
            <div class="chart-bar-fill" style="width: ${pct}%"></div>
          </div>
          <div class="chart-bar-value">${val}</div>
        </div>
      `;
    }).join("");
  }
  
  if (weeklyContainer) {
    // Thống kê 7 ngày qua
    const weekdayNames = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
    const stats = [];
    
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const dateStr = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
      const count = state.attendance.filter(log => checkDateMatch(log.check_in_time, dateStr)).length;
      stats.push({
        label: weekdayNames[d.getDay()],
        val: count
      });
    }
    
    const maxWeekly = Math.max(...stats.map(s => s.val), 1);
    
    weeklyContainer.innerHTML = stats.map(s => {
      const pct = Math.round((s.val / maxWeekly) * 80) + 5; // Bảo đảm cao ít nhất 5%
      return `
        <div class="weekly-col">
          <div class="weekly-bar-wrap">
            <div class="weekly-bar" style="height: ${pct}%">
              <span class="weekly-tooltip">${s.val} lượt quét</span>
            </div>
          </div>
          <span class="weekly-label">${s.label}</span>
        </div>
      `;
    }).join("");
  }
}

// ─── WEBCAM CAMERA OPERATIONS ─────────────────────────────
async function startCamera() {
  try {
    await request("/api/camera/start", { method: "POST" });
    showToast("Đã gửi lệnh khởi động Camera.");
    setTimeout(() => {
      const preview = $("#cameraPreview");
      if (preview) preview.src = `/api/camera/stream?t=${Date.now()}`;
    }, 1500);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function stopCamera() {
  try {
    await request("/api/camera/stop", { method: "POST" });
    showToast("Đã tắt luồng Camera.");
    const preview = $("#cameraPreview");
    if (preview) preview.src = "";
    $("#adminCamWaiting")?.classList.remove("hidden");
  } catch (error) {
    showToast(error.message, true);
  }
}

// ─── WEBSOCKET REALTIME EVENTS ────────────────────────────
function connectWebSocket() {
  if (state.ws) return;

  const loc = window.location;
  const proto = loc.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${loc.host}/ws/attendance`;

  state.ws = new WebSocket(wsUrl);

  state.ws.onopen = () => {
    const dot = $("#wsDot");
    const status = $("#wsStatus");
    if (dot && status) {
      dot.className = "status-dot online";
      status.textContent = "Hệ thống Online";
    }
  };

  state.ws.onmessage = event => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.event === "checkin_success" || msg.event === "already_checked_in") {
        // Thêm sự kiện realtime
        addRealtimeEvent(msg);
        
        // Cập nhật bảng và biểu đồ nếu đang hiển thị
        refreshAll();
      }
    } catch (e) {
      console.warn("WebSocket parse error:", e);
    }
  };

  state.ws.onclose = () => {
    state.ws = null;
    const dot = $("#wsDot");
    const status = $("#wsStatus");
    if (dot && status) {
      dot.className = "status-dot";
      status.textContent = "Hệ thống Offline";
    }
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = setTimeout(connectWebSocket, 3000);
  };
}

function addRealtimeEvent(data) {
  const feed = $("#eventFeed");
  if (!feed) return;

  const empty = feed.querySelector(".empty-text");
  if (empty) empty.remove();

  const time = new Date(data.check_in_time || data.checkin_time || new Date()).toLocaleTimeString("vi-VN", { hour12: false });
  const row = document.createElement("div");
  row.className = `event-row ${data.arrival_status === "late" ? "danger" : "success"}`;
  row.style.display = "flex";
  row.style.alignItems = "center";
  row.style.gap = "10px";
  row.style.padding = "8px 12px";
  row.style.borderBottom = "1px solid var(--line)";
  row.style.fontSize = "13px";

  row.innerHTML = `
    <span style="width: 70px; flex-shrink: 0; font-weight:700; color:var(--muted);">${time}</span>
    <div style="flex-grow: 1; flex-shrink: 1; min-width: 0; display:flex; flex-direction:column; gap:2px; padding-right: 10px;">
      <span style="font-weight:700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeText(data.full_name)}</span>
      <span style="font-size:11px; color:var(--muted); font-family:monospace;">${escapeText(data.user_code || data.student_code || '—')}</span>
    </div>
    <span style="width: 180px; flex-shrink: 0; font-size:12px; color:var(--primary); font-weight:600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">[${escapeText(data.department || "Nhân sự")}]</span>
    <span style="width: 90px; flex-shrink: 0; text-align: right; font-weight:700; color:${data.arrival_status === 'late' ? 'var(--danger)' : 'var(--success)'};">
      ${data.arrival_status === 'late' ? 'VÀO MUỘN' : 'ĐÚNG GIỜ'}
    </span>
  `;

  feed.insertBefore(row, feed.firstChild);

  // Giới hạn tối đa 15 dòng log realtime
  const rows = feed.querySelectorAll(".event-row");
  if (rows.length > 15) {
    rows[rows.length - 1].remove();
  }
}

// ─── UTILITIES ────────────────────────────────────────────
function showToast(msg, isError = false) {
  const t = $("#toast");
  if (!t) return;
  t.textContent = msg;
  t.className = `toast show ${isError ? "error" : "success"}`;
  setTimeout(() => t.classList.remove("show"), 3500);
}

function setBusy(el, isBusy, text = "") {
  if (!el) return;
  el.disabled = isBusy;
  if (isBusy) {
    el.dataset.prevText = el.textContent;
    el.textContent = text + "...";
  } else {
    el.textContent = el.dataset.prevText || el.textContent;
  }
}

function escapeText(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatDateTime(str) {
  if (!str) return "—";
  try {
    const date = new Date(str);
    return date.toLocaleString("vi-VN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return str;
  }
}

function renderTableError(id, colspan, err) {
  const el = $(`#${id}`);
  if (el) el.innerHTML = `<tr><td colspan="${colspan}" class="empty-row error-text">Lỗi: ${err.message}</td></tr>`;
}

function renderFilePreview(files, target) {
  if (!target) return;
  target.innerHTML = "";
  Array.from(files || []).slice(0, 6).forEach(file => {
    if (!file.type.startsWith("image/")) return;
    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.style.width = "50px";
    img.style.height = "50px";
    img.style.objectFit = "cover";
    img.style.borderRadius = "6px";
    img.style.border = "1px solid var(--line)";
    img.onload = () => URL.revokeObjectURL(img.src);
    target.appendChild(img);
  });
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function nullableValue(val) {
  const t = val.trim();
  return t ? t : null;
}

function checkDateMatch(dbDateStr, filterDateStr) {
  if (!filterDateStr) return true;
  if (!dbDateStr) return false;
  const d = new Date(dbDateStr);
  if (isNaN(d.getTime())) return false;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}` === filterDateStr;
}

// ─── SYSTEM LOGS ──────────────────────────────────────────
async function loadSystemLogs() {
  try {
    const type = $("#syslogTypeFilter")?.value || "";
    const dateVal = $("#syslogDateFilter")?.value || "";
    const search = $("#syslogSearchFilter")?.value.trim().toLowerCase() || "";

    let url = `/api/system/logs?limit=300`;
    if (type) url += `&event_type=${encodeURIComponent(type)}`;

    const data = await request(url);
    let logs = data.logs || [];

    if (dateVal) {
      logs = logs.filter(log => checkDateMatch(log.created_at, dateVal));
    }

    if (search) {
      logs = logs.filter(log => 
        (log.message && log.message.toLowerCase().includes(search)) || 
        (log.detail && log.detail.toLowerCase().includes(search))
      );
    }

    state.systemLogs = logs;
    renderSystemLogs();
  } catch (error) {
    renderTableError("syslogTableBody", 4, error);
  }
}

function renderSystemLogs() {
  const body = $("#syslogTableBody");
  if (!body) return;

  $("#systemLogsCountText").textContent = `${state.systemLogs.length} bản ghi`;

  if (!state.systemLogs.length) {
    body.innerHTML = `<tr><td colspan="4" class="empty-row">Không tìm thấy sự kiện hệ thống nào.</td></tr>`;
    return;
  }

  const badgeMap = {
    checkin: '<span class="badge badge-success">CHECK-IN</span>',
    register: '<span class="badge badge-primary">REGISTER</span>',
    auth: '<span class="badge badge-warning">AUTH</span>',
    system: '<span class="badge badge-secondary">SYSTEM</span>'
  };

  body.innerHTML = state.systemLogs.map(log => `
    <tr>
      <td>${formatDateTime(log.created_at)}</td>
      <td>${badgeMap[log.event_type] || `<span class="badge badge-secondary">${escapeText(log.event_type)}</span>`}</td>
      <td><div class="cell-main" style="text-align:left; font-weight:600;">${escapeText(log.message)}</div></td>
      <td><div class="cell-sub" style="text-align:left; font-family:monospace; font-size:12px;">${escapeText(log.detail || "—")}</div></td>
    </tr>
  `).join("");
}

function clearSyslogFilter() {
  if ($("#syslogTypeFilter")) $("#syslogTypeFilter").value = "";
  if ($("#syslogDateFilter")) $("#syslogDateFilter").value = "";
  if ($("#syslogSearchFilter")) $("#syslogSearchFilter").value = "";
  loadSystemLogs();
}

