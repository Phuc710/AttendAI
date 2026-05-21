# Face Attendance System

Hệ thống điểm danh khuôn mặt nhiều người đồng thời — không train model.

## Cài Đặt

```bash
cd face-attendance/

python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt

cp .env.example .env
# Chỉnh CAMERA_SOURCE=0 nếu dùng USB camera
```

## Chạy

```bash
cd backend/
python main.py
```

## Truy Cập

| URL | Mô tả |
|-----|-------|
| http://localhost:8000/kiosk | Màn hình kiosk (điểm danh) |
| http://localhost:8000/admin | Admin dashboard |
| http://localhost:8000/docs  | API docs (Swagger) |
| ws://localhost:8000/ws/attendance | WebSocket realtime |

## Quy Trình Demo

1. Mở Admin → Sinh Viên → Thêm sinh viên
2. Admin → Enrollment → Upload ảnh mỗi người
3. Admin → Phiên Học → Bắt đầu session
4. Admin → Hệ Thống → Bật Camera
5. Mở Kiosk URL trên màn hình cảm ứng
6. Sinh viên đi vào vùng camera → điểm danh tự động

## Cấu Trúc

```
face-attendance/
├── backend/
│   ├── main.py          # FastAPI entry point
│   ├── config.py        # Cấu hình từ .env
│   ├── database.py      # SQLite init + helpers
│   ├── api/             # REST routes
│   └── services/        # AI, camera, attendance, WS
├── frontend/
│   ├── kiosk/           # Màn hình điểm danh
│   └── admin/           # Dashboard quản trị
├── .env.example
└── requirements.txt
```
