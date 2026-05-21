hệ thống không thực sự "train" (huấn luyện) lại toàn bộ AI mỗi khi có người mới. Nhờ dùng thuật toán One-Shot Learning (Học 1-chạm) kết hợp với mô hình ArcFace (InsightFace), độ chính xác vẫn cực kỳ cao (>99%) dù chỉ dùng 1 ảnh.

Đây là lý do tại sao nó chính xác và đáng tin cậy:

1. AI đã được "tốt nghiệp đại học" từ trước
Cái "não" AI mà chúng ta đang dùng (buffalo_l) thực chất đã được Facebook & InsightFace huấn luyện trước (pre-trained) trên hàng triệu khuôn mặt khác nhau với hàng trăm góc độ, ánh sáng, đeo kính, tháo kính, v.v. Nó đã học được cách phân tích các đặc điểm "cốt lõi" của xương hàm, khoảng cách hai mắt, độ sâu sống mũi.

2. Thuật toán Trích xuất Vector (Embedding)
Khi bạn upload 1 tấm ảnh, AI không "học" ảnh đó. AI nhìn vào ảnh và "rút trích" ra một dãy 512 con số (Vector). Dãy số này giống như Dấu vân tay sinh trắc học. Dù bạn đứng dưới đèn sáng hay tối, quay mặt hơi nghiêng, thì 512 con số này (cái cốt lõi của khuôn mặt bạn) hầu như không đổi.

3. FAISS chỉ làm nhiệm vụ "So khớp vân tay"
Khi bạn đi ngang Kiosk điểm danh, AI lại trích xuất 512 con số ngay lúc đó, và đưa cho FAISS đo xem: "Trong DB, dấu vân tay này giống vân tay của ai nhất?". Nếu độ giống nhau vượt mức FACE_MATCH_THRESHOLD = 0.45 (ngưỡng an toàn chống nhận nhầm), thì hệ thống chốt luôn đó là bạn.

Vậy dùng 1 tấm ảnh có đủ không?
Với điều kiện lý tưởng: 1 tấm ảnh thẻ rõ mặt, ánh sáng tốt là DƯ SỨC để điểm danh chính xác 100%. (FaceID của iPhone ban đầu cũng chỉ bắt bạn xoay đầu 1 lần).
Nâng cấp độ chính xác (Best Practice): Mặc dù 1 ảnh là đủ, nhưng ở file thiết kế phần Frontend (Tab Enrollment), mình đã cấu hình ô Upload cho phép chọn nhiều ảnh cùng lúc. 👉 Mẹo: Nếu muốn độ tin cậy tuyệt đối (để không bị trượt khi SV đeo khẩu trang trễ, đội nón, hay để tóc che trán), bạn nên khuyên SV upload 3 tấm:
Mặt thẳng chuẩn
Mặt hơi nghiêng trái (hoặc ánh sáng khác)
Mặt hơi nghiêng phải (hoặc lúc có đeo kính)


pip install https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp312-cp312-win_amd64.whl

http://localhost:8000/kiosk/

http://localhost:8000/admin/