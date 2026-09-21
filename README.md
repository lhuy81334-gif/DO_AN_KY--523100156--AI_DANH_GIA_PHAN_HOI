# Seller Feedback Intelligence

Hệ thống FastAPI + MongoDB + React chạy localhost để thu thập review Tiki/Lazada, phân tích độ tin cậy, kiểm tra ảnh review và gợi ý hành động cho seller.

## Mục Tiêu

Seller không cần đọc thủ công hàng trăm review. Hệ thống tập trung trả lời 4 câu hỏi:

- Ảnh trong review có phù hợp với sản phẩm không?
- Review có đủ bằng chứng để dùng làm insight không?
- Review đáng tin ở mức nào?
- Seller có cần kiểm tra, xử lý hoặc khiếu nại không?

## MongoDB

Database mặc định: `POD`.

Các collection chính cần quan tâm:

```text
platforms
shops
products
reviews
review_aspects
review_trust_analyses
ingestion_jobs
counters
```

Các Mongo view hỗ trợ tách dữ liệu theo sàn:

```text
reviews_tiki
reviews_lazada
reviews_with_images
reviews_tiki_with_images
reviews_lazada_with_images
reviews_need_seller_attention
reviews_tiki_need_seller_attention
reviews_lazada_need_seller_attention
```

## Cài Đặt

```powershell
cd C:\Users\Admin\Desktop\DoANTotNghiep\pod-ai-evaluator
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

Nếu cần tạo file môi trường:

```powershell
copy backend\.env.example backend\.env
```

## Chạy Backend

```powershell
cd C:\Users\Admin\Desktop\DoANTotNghiep\pod-ai-evaluator\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Nếu PowerShell báo sai đường dẫn, dùng lệnh này từ thư mục gốc project:

```powershell
cd C:\Users\Admin\Desktop\DoANTotNghiep\pod-ai-evaluator
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Swagger API: http://localhost:8000/docs

## Chạy Frontend

```powershell
cd C:\Users\Admin\Desktop\DoANTotNghiep\pod-ai-evaluator\frontend
npm install
npm run dev
```

Dashboard: http://localhost:5173

## Kéo Review Tiki

Tiki có thể gọi bằng API review trực tiếp:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_tiki_reviews.py --product-id 86517373 --spid 86517374 --page-size 20 --max-pages-per-star 20 --delay 1
```

Kéo nhiều sản phẩm bằng CSV:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_tiki_reviews.py --products-file data\api\tiki\products_to_fetch.csv --page-size 20 --max-pages-per-star 20 --delay 1
```

File CSV:

```csv
product_id,spid
86517373,86517374
```

## Kéo Review Lazada

Lazada dùng MTOP nên cần cookie/token từ browser. Dùng Network tab, chọn request review, `Copy as cURL`, lưu vào một file `.txt`, rồi chạy:

```powershell
.\.venv\Scripts\python.exe scripts\configure_lazada_env.py data\private\lazada_curl.txt
```

Sau đó fetch review:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_lazada_reviews.py --item-id 310626559 --page-size 5 --max-pages-per-star 20 --delay 2
```

Fetch riêng nhóm review có ảnh/video:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_lazada_reviews.py --item-id 310626559 --page-size 5 --max-pages-per-star 20 --delay 2 --with-images-only
```

Script sẽ tự ký `sign` mới từ `_m_h5_tk` trong cookie.

## Phân Tích Review

Chấm độ tin cậy review:

```powershell
.\.venv\Scripts\python.exe scripts\analyze_review_trust.py --limit 0
```

Đọc ảnh review và so với sản phẩm:

```powershell
.\.venv\Scripts\python.exe scripts\analyze_review_images.py --product-id 71 --limit 0 --max-images-per-review 2
```

Tạo lại các view tách Tiki/Lazada:

```powershell
.\.venv\Scripts\python.exe scripts\create_mongo_review_views.py
```

## Luồng Làm Việc

1. Kéo review từ Tiki/Lazada.
2. Import hoặc để script import thẳng vào MongoDB.
3. Chạy trust analysis.
4. Chạy image analysis cho review có ảnh.
5. Chạy create views để Compass có các mục tách riêng.
6. Mở dashboard React hoặc Swagger để xem seller feedback.

## File Chính

```text
scripts/fetch_tiki_reviews.py
scripts/fetch_lazada_reviews.py
scripts/analyze_review_trust.py
scripts/analyze_review_images.py
scripts/create_mongo_review_views.py
backend/app/services/seller_feedback.py
backend/app/ml/review_trust.py
backend/app/ml/image_evidence.py
frontend/src/App.tsx
```
