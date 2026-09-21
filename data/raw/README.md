# Raw CSV/JSON data

Đây là nơi đặt dữ liệu thật đã được chuẩn hóa hoặc export thủ công.

## Products schema

```text
external_product_id,title,description,category,price,currency,rating,review_count,sold_count,product_url
```

`category` tạm thời ưu tiên:

```text
ao
quan
```

## Reviews schema

```text
external_product_id,external_review_id,rating,review_text,review_language,review_like_count
```

Import:

```powershell
python scripts\import_products.py data\raw\products.csv --platform lazada
python scripts\import_reviews.py data\raw\reviews.csv --platform lazada
```
