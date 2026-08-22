# 🎯 AttendAI — Hệ Thống Điểm Danh Khuôn Mặt Thông Minh

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/InsightFace-Buffalo__L-FF6F00?style=for-the-badge&logo=onnx&logoColor=white" alt="InsightFace" />
  <img src="https://img.shields.io/badge/OpenCV-4.9+-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white" alt="OpenCV" />
  <img src="https://img.shields.io/badge/FAISS-Vector_Search-00599C?style=for-the-badge" alt="FAISS" />
  <img src="https://img.shields.io/badge/SQLite-WAL_Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
</p>

---

## 📖 Giới Thiệu

**AttendAI** là giải pháp điểm danh nhận diện khuôn mặt tự động thời gian thực (Real-time Face Recognition Attendance System), ứng dụng công nghệ thị giác máy tính tiên tiến (**InsightFace ArcFace 512-D Embeddings**) kết hợp tìm kiếm vector siêu tốc (**FAISS**). Hệ thống được tối ưu hóa cho môi trường trường học, doanh nghiệp và sự kiện với giao diện Kiosk thân thiện và bảng quản trị tập trung.

---

## ✨ Tính Năng Nổi Bật

- ⚡ **Nhận diện Realtime siêu tốc:** Xử lý luồng camera liên tục, nhận diện khuôn mặt đa luồng với độ chính xác cao nhờ model `buffalo_l`.
- 🔍 **Vector Indexing (FAISS):** Tối ưu hóa tốc độ so khớp vector 512 chiều dưới 1 mili-giây, hỗ trợ hàng ngàn nhân sự/học viên.
- 🛡️ **Duplicate Guard & Anti-Spam:** Tự động lọc trùng lặp trong khoảng thời gian tùy chỉnh (`DUPLICATE_TIME_WINDOW`), chống spam điểm danh.
- 📸 **Lưu trữ Snapshot tự động:** Ghi lại hình ảnh khoảnh khắc điểm danh thực tế làm minh chứng đối soát.
- 👤 **Cổng Tự Đăng Ký (Self-service Enrollment):** Cho phép người dùng chụp ảnh trực tiếp qua webcam hoặc tải ảnh chân dung với bộ lọc chất lượng khuôn mặt (`quality_score`).
- 📊 **Bảng Quản Trị Toàn Diện (Admin Dashboard):**
  - Quản lý phiên điểm danh / ca học / ca làm việc.
  - Quản lý nhân sự, phòng ban, phân quyền nhóm.
  - Lịch sử điểm danh kèm ảnh snapshot, trạng thái đúng giờ/đi trễ (`arrival_status`).
  - WebSocket truyền tải nhật ký sự kiện (Audit Log) theo thời gian thực.
  - Giám sát trạng thái luồng camera và tùy chỉnh cấu hình trực tiếp.

---

## 🖼️ Giao Diện Demo (UI Showcase)

### 1. Bảng Điều Khiển Quản Trị (Admin Dashboard)
Tổng quan thống kê sĩ số, tỷ lệ điểm danh, ca trực hoạt động và biểu đồ trực quan:
![Admin Dashboard](UI_Demo/Admin_dashboard.png)

---

### 2. Quản Lý Nhân Sự & Danh Sách (User Management)
Danh sách thành viên, thông tin mã định danh, phòng ban và tình trạng đăng ký vector khuôn mặt:
![Admin List Users](UI_Demo/Admin_ListUser.png)

---

### 3. Lịch Sử Điểm Danh (Attendance History)
Chi tiết lịch sử ra vào, thời gian check-in/out, độ tin cậy AI (Confidence) và ảnh snapshot thực tế:
![Admin History](UI_Demo/Admin_history.png)

---

### 4. Nhật Ký Sự Kiện Thời Gian Thực (Live Audit Logs)
Luồng log thời gian thực kết nối qua WebSocket thông báo tức thì các sự kiện nhận diện và cảnh báo:
![Admin Logs](UI_Demo/Admin_Log.png)

---

### 5. Đăng Ký Khuôn Mặt Mới (Face Registration Portal)
Giao diện đăng ký tự phục vụ hỗ trợ chụp ảnh trực tiếp qua webcam hoặc tải ảnh chân dung:

| Đăng Ký Mới | Xác Nhận Thành Công |
| :---: | :---: |
| ![Register](UI_Demo/register.png) | ![Register Success](UI_Demo/registor_success.png) |

---

## 🏗️ Kiến Trúc Hệ Thống

```mermaid
flowchart TD
    subgraph Camera_Service["Camera & AI Ingestion"]
        CAM["Webcam / RTSP Stream"] -->|Frame Stream| CV["OpenCV Ingest"]
        CV -->|Frame Skip & Resize| DET["InsightFace (buffalo_l)"]
        DET -->|Extract 512D Vector| VEC["Face Embeddings"]
    end

    subgraph Matching_Engine["Core Matching & Indexing"]
        VEC --> MATCH["FAISS Cosine Search"]
        MATCH -->|Score >= Threshold| DUP["Duplicate Guard (30s)"]
        DUP -->|Pass| REC["Record Attendance"]
    end

    subgraph Backend_Database["Storage & Realtime"]
        REC --> DB[(SQLite DB - WAL)]
        REC --> SNAP["Save Snapshot Image"]
        REC --> WS["WebSocket Broadcaster"]
    end

    subgraph Client_Applications["Frontend Interfaces"]
        WS -->|Live Updates| KIOSK["Kiosk Check-in UI"]
        WS -->|Realtime Logs| ADMIN["Admin Portal Dashboard"]
    end
```

---

## 🛠️ Công Nghệ Sử Dụng (Tech Stack)

| Thành phần | Công nghệ / Thư viện | Mô tả |
| :--- | :--- | :--- |
| **Backend Core** | `Python 3.12`, `FastAPI`, `Uvicorn` | RESTful API hiệu năng cao, cơ chế Asynchronous Lifespan |
| **Computer Vision & AI** | `InsightFace (ArcFace)`, `ONNX Runtime` | Phát hiện khuôn mặt và trích xuất vector 512 chiều |
| **Vector Search** | `FAISS-CPU` | Thuật toán lập chỉ mục và tìm kiếm lân cận siêu tốc |
| **Video Processing** | `OpenCV (cv2)` | Thu thập luồng camera USB / RTSP IP Camera |
| **Database & Cache** | `SQLite 3 (WAL Mode)` | Lưu trữ dữ liệu quan hệ, log điểm danh và đường dẫn snapshot |
| **Realtime Engine** | `FastAPI WebSockets` | Đồng bộ dữ liệu 2 chiều giữa Server và Admin/Kiosk Client |
| **Frontend** | `Vanilla HTML5`, `CSS3`, `Modern JavaScript` | Giao diện Responsive hiện đại, tối ưu tốc độ tải trang |

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy

### 1. Yêu cầu tiên quyết
- **Hệ điều hành:** Windows 10/11 64-bit hoặc Linux
- **Python:** Khuyến nghị **Python 3.12 (64-bit)**
- **Webcam:** Camera tích hợp laptop hoặc Webcam USB / RTSP IP Camera

---

### 2. Cài đặt môi trường

#### Bước 1: Clone kho lưu trữ
```bash
git clone https://github.com/Phuc710/AttendAI.git
cd AttendAI
```

#### Bước 2: Tạo môi trường ảo (Khuyến nghị)
```bash
python -m venv venv
# Trên Windows:
venv\Scripts\activate
# Trên Linux/macOS:
source venv/bin/activate
```

#### Bước 3: Cài đặt các gói phụ thuộc
```bash
pip install -r requirements.txt
```

> **Lưu ý trên Windows:** File `requirements.txt` đã cấu hình sẵn bánh xe cài đặt (`wheel`) của InsightFace tương thích chuẩn với Python 3.12 64-bit:
> ```bash
> pip install https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp312-cp312-win_amd64.whl
> ```

---

### 3. Cấu hình biến môi trường (`.env`)

Tạo file `.env` tại thư mục `backend/.env` (hoặc sao chép từ `.env.example`):

```ini
# ─── SERVER ───
HOST=0.0.0.0
PORT=8000
ADMIN_PASSWORD=admin123

# ─── CAMERA ───
# "0" là camera mặc định (USB/Laptop). Đối với IP Camera, nhập đường dẫn RTSP:
# CAMERA_SOURCE=rtsp://admin:pass@192.168.1.50:554/stream1
CAMERA_SOURCE=0
CAMERA_WIDTH=1280
CAMERA_HEIGHT=720
CAMERA_FPS=30
FRAME_SKIP=3

# ─── AI MODEL ───
MODEL_NAME=buffalo_l
FACE_MATCH_THRESHOLD=0.50
MIN_FACE_SIZE=60
MIN_DET_SCORE=0.50

# ─── STORAGE & LOGIC ───
SAVE_UNKNOWN_FACE=false
SAVE_ATTENDANCE_SNAPSHOT=true
DUPLICATE_TIME_WINDOW=30
```

---

### 4. Khởi chạy hệ thống

Di chuyển vào thư mục `backend` và chạy:

```bash
cd backend
python main.py
```

*Trong lần khởi chạy đầu tiên, hệ thống sẽ tự động tải model AI `buffalo_l` (~280MB) và khởi tạo database.*

---

## 🌐 Đường Dẫn Truy Cập Ứng Dụng

Sau khi server khởi động thành công:

| Giao diện / Tính năng | URL | Mô tả |
| :--- | :--- | :--- |
| **Kiosk Điểm Danh** | [http://localhost:8000/kiosk/](http://localhost:8000/kiosk/) | Màn hình quét khuôn mặt tự động |
| **Đăng Ký Khuôn Mặt** | [http://localhost:8000/kiosk/register.html](http://localhost:8000/kiosk/register.html) | Cổng đăng ký khuôn mặt nhân sự mới |
| **Admin Panel** | [http://localhost:8000/admin/](http://localhost:8000/admin/) | Bảng điều khiển quản trị (Pass mặc định: `admin123`) |
| **Swagger API Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | Tài liệu kiểm thử toàn bộ REST API |

---

## 📂 Cấu Trúc Dự Án

```text
AttendAI/
├── .env.example              # Mẫu cấu hình môi trường
├── requirements.txt          # Danh sách dependencies
├── note.md                   # Ghi chú kỹ thuật nhanh
├── README.md                 # Tài liệu hướng dẫn dự án
├── UI_Demo/                  # Ảnh chụp giao diện thực tế
│   ├── Admin_dashboard.png
│   ├── Admin_ListUser.png
│   ├── Admin_history.png
│   ├── Admin_Log.png
│   ├── register.png
│   └── registor_success.png
├── backend/                  # Mã nguồn Backend FastAPI
│   ├── api/                  # REST API Endpoints (Users, Groups, Sessions, Attendance, Camera, System, Configs)
│   ├── services/             # Core Logic (Face, Match, Attendance, Camera, WebSocket)
│   ├── config.py             # Quản lý cấu hình & hằng số hệ thống
│   ├── database.py           # Schema SQLite & các truy vấn CSDL
│   ├── main.py               # Điểm khởi chạy chính ứng dụng FastAPI
│   └── storage/              # Thư mục lưu ảnh đã đăng ký, snapshot, ảnh người lạ
└── frontend/                 # Giao diện Web
    ├── admin/                # Trang quản trị (index.html, admin.css, admin.js)
    └── kiosk/                # Giao diện điểm danh & đăng ký (index.html, register.html, ...)
```

---

## 🔒 Bản Quyền & Giấy Phép

Phát triển bởi **Phuc710** — Mã nguồn mở phục vụ mục đích học tập và nghiên cứu. Mọi đóng góp và báo lỗi (Issue / Pull Request) luôn được chào đón! 🚀