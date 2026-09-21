# Lazada API data

Đây là nơi bạn đặt dữ liệu thật/export response liên quan Lazada.

Không đặt Cookie, token, sign, x-ua, session hoặc secret vào folder này.

## Fetch review API

Sau khi cấu hình Cookie từ cURL bằng `scripts\configure_lazada_env.py`, chạy:

```powershell
python scripts\fetch_lazada_reviews.py --item-id LAZADA_ITEM_ID --page-size 5 --max-pages-per-star 20 --delay 2
```

Muốn import luôn vào MongoDB thì thêm `--import-to-mongo`.

## Sản phẩm áo/quần

Sản phẩm nên được đưa vào `data/raw/products.csv` hoặc `data/raw/products.json`, rồi import bằng:

```powershell
python scripts\import_products.py data\raw\products.csv --platform lazada
```
