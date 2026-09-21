1. Thông tin sinh viên:
Họ & tên: Lương Trọng
MSSV: 523100156
Lớp: 523100C
GVHD: ThS. Trần Thị HIền
2. Mục tiêu đề tài
  Hệ thông giải quyết bài toán người bán phải đọc nhiều phản hồi của khách hàng bằng cách xem thủ công trên sàn TMDT. Ứng dụng này sẽ xác định tính xác thực của đánh giá:
kiểm tra ảnh đính kèm có đúng với sản phẩm thực tế hay không giúp người bán xử lý lỗi hoặc gửi khiếu nại lên sàn.
3. Chức năng cốt lõi
  - Thu nhập dữ liệu trên sàn TMDT
  - Tính ra độ tin cậy của các phản hồi
  - Thẩm định, xác thực bằng hình
4. Công nghệ sử dụng
  - Front-end: TypeScript, TailwindCSS.
  - Back-end: Python, FastAPI, Pydantic.
  - Database: MongoDB.
  - Testing: Pytest
  - Version Control: Git/GitHub.
5. Hướng dẫn cài đặt/chạy.
  - Cài thư viện backend: cd C:\Users\Admin\Desktop\DoANTotNghiep\pod-ai-evaluator
                          .\.venv\Scripts\pip.exe install -r requirements.txt
  - Chạy MongoDB: Open Mongo
  - Chạy backend FastAPI: cd C:\Users\Admin\Desktop\DoANTotNghiep\pod-ai-evaluator\backend
                          ..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
  - Chạy frontend: cd C:\Users\Admin\Desktop\DoANTotNghiep\pod-ai-evaluator\frontend
                    npm install
                    npm run dev -- --host 127.0.0.1 --port 5173
    Kiểm tra tại: http://127.0.0.1:5173
6. Tiến độ
  - Checkpoint 01: Khảo sát bài toán thực tế, xác định mục tiêu và lập đề cương kỹ thuật.
  - Checkpoint 02: Đặc tả yêu cầu CLO2, thiết kế Use Case, xây dựng kiến trúc Data Ingestion (Tiki/Lazada) và mô hình hóa dữ liệu MongoDB.
  - Checkpoint 03: Hoàn thiện Backend FastAPI, cấu hình Pipeline Ingestion và triển khai hệ thống lưu trữ view phân tách sàn.
  - Checkpoint 04: Tích hợp module AI kiểm định bằng chứng ảnh review (image_evidence.py) và thuật toán tính Trust Score (review_trust.py).
  - Checkpoint 05: Kết nối Dashboard React với API backend, hoàn thiện tính năng gợi ý hành động Seller Feedback.
  - Checkpoint 06: Đánh giá độ chuẩn xác, tối ưu thời gian phản hồi, kiểm thử toàn diện và hoàn thiện khóa luận tốt nghiệp.
