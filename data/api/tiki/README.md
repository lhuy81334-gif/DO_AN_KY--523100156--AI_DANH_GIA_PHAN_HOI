# Tiki API data

Đây là nơi lưu response thật từ Tiki review API và file normalized dùng để import MongoDB.

Fetch trực tiếp review Tiki:

```powershell
python scripts\fetch_tiki_reviews.py --product-id 86517373 --spid 86517374 --page-size 20 --max-pages-per-star 20 --delay 1
```

Fetch nhiều sản phẩm:

```powershell
python scripts\fetch_tiki_reviews.py --products-file data\api\tiki\products_to_fetch.csv --page-size 20 --max-pages-per-star 20 --delay 1
```

Script sẽ lưu:

```text
data/api/tiki/all_stratified_reviews_86517373.json
data/api/tiki/all_stratified_reviews_86517373_normalized.json
```

Nếu muốn import review vào MongoDB luôn:

```powershell
python scripts\fetch_tiki_reviews.py --product-id 86517373 --spid 86517374 --page-size 20 --max-pages-per-star 20 --delay 1 --import-to-mongo
```

Lưu ý: muốn import review thành công thì collection `products` phải có sản phẩm Tiki với `external_product_id=86517373`.

Nếu bạn đã có file products/reviews schema chung, vẫn có thể import bằng:

```powershell
python scripts\import_products.py data\raw\tiki_products.csv --platform tiki
python scripts\import_reviews.py data\raw\tiki_reviews.csv --platform tiki
```
