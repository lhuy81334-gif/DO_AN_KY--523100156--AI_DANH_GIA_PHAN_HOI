# API response data

Folder này dành cho dữ liệu thật bạn tự lấy hoặc export hợp lệ từ nguồn của bạn.

Không lưu các thông tin bảo mật như Cookie, access token, session token, CSRF token, sign, x-ua hoặc password vào repository.

Cấu trúc gợi ý:

```text
data/api/tiki/all_stratified_reviews_86517373.json
data/api/lazada/product_001_reviews_page_1.json
data/api/lazada/product_001_reviews_page_2.json
```

Script chính:

```powershell
python scripts\fetch_tiki_reviews.py --products-file data\api\tiki\products_to_fetch.csv --delay 0.3
python scripts\fetch_lazada_reviews.py --item-id LAZADA_ITEM_ID --page 1 --page-size 10
```

Muốn import vào MongoDB thì thêm `--import-to-mongo`, nhưng product phải tồn tại trước trong collection `products`.
