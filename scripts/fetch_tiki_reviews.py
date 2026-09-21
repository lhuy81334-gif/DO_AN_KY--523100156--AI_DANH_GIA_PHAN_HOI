import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR / "backend"))

from app.db.database import db, ensure_indexes
from app.ingestion.json_importer import JSONImporter
from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.product_repo import ProductRepository


TIKI_REVIEW_URL = "https://tiki.vn/api/v2/reviews"
OUTPUT_DIR = ROOT_DIR / "data/api/tiki"
DEFAULT_PRODUCT_ID = "86517373"
DEFAULT_SPID = "86517374"
DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_PAGES_PER_STAR = 20
DEFAULT_DELAY = 1.0
DEFAULT_IMPORT_TO_MONGO = True


def fetch_all_reviews_by_stars(
    product_id: str,
    spid: str,
    page_size: int = 20,
    max_pages_per_star: int = 20,
    delay: float = 1.0,
) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    session = requests.Session()
    session.trust_env = False
    session.headers.update(headers)

    all_collected_reviews: list[dict[str, Any]] = []
    stars_list = [5, 4, 3, 2, 1]

    print(f"Bat dau thu thap review cho san pham {product_id}, spid {spid}...")

    for star in stars_list:
        print(f"\n--- Dang vet toan bo danh gia {star} sao ---")
        page = 1
        star_count = 0

        while True:
            payload = {
                "limit": page_size,
                "include": "comments,contribute_info,attribute_vote_summary",
                "sort": f"stars|{star}",
                "page": page,
                "spid": spid,
                "product_id": product_id,
                "seller_id": 1,
            }

            try:
                res = session.get(TIKI_REVIEW_URL, params=payload, timeout=10)
                if res.status_code != 200:
                    print(f"  [!] {star} sao: Dung o trang {page} (HTTP {res.status_code})")
                    break

                data = res.json()
                reviews = data.get("data", [])

                if not reviews:
                    print(f"  [i] Da vet het review cua muc {star} sao (Tong: {star_count})")
                    break

                sample_label = "HIGH_RATING" if star >= 4 else "LOW_RATING"
                if star == 3:
                    sample_label = "NEUTRAL_RATING"

                for review in reviews:
                    review["sample_type"] = sample_label
                    all_collected_reviews.append(review)

                star_count += len(reviews)
                print(f"  [+] {star} sao - Trang {page}: gom them {len(reviews)} review (Luy ke: {star_count})")

                if page >= max_pages_per_star:
                    print(f"  [i] Dung o gioi han {max_pages_per_star} trang cho muc {star} sao")
                    break

                page += 1
                if delay > 0:
                    time.sleep(delay)

            except requests.exceptions.RequestException as exc:
                print(f"  [x] Loi mang tai trang {page}: {exc}")
                break

    print("\n" + "=" * 50)
    print(f"Tong ket: Da gom duoc {len(all_collected_reviews)} review tren toan bo 5 dai sao.")
    return all_collected_reviews


def normalize_tiki_reviews(reviews: list[dict[str, Any]], external_product_id: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for review in reviews:
        text = str(review.get("content") or "").strip()
        if not text:
            continue
        normalized.append(
            {
                "external_product_id": external_product_id,
                "external_review_id": str(review.get("id") or ""),
                "source": "TIKI",
                "platform_code": "tiki",
                "rating": float(review.get("rating") or 5),
                "review_text": text,
                "review_language": "vi",
                "review_like_count": int(review.get("thank_count") or 0),
                "sample_type": review.get("sample_type", ""),
                "raw_created_at": review.get("created_at"),
                "raw_title": review.get("title", ""),
                "spid": review.get("spid"),
                "seller_id": (review.get("seller") or {}).get("id"),
                "images": review.get("images") or [],
                "image_urls": [
                    image.get("full_path")
                    for image in (review.get("images") or [])
                    if isinstance(image, dict) and image.get("full_path")
                ],
            }
        )
    return normalized


def save_json(data: Any, filename: Path) -> None:
    filename.parent.mkdir(parents=True, exist_ok=True)
    with filename.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    print(f"Da luu vao: {filename}")


def ensure_minimal_product(external_product_id: str, platform_code: str, title: str) -> None:
    platform = PlatformRepository(db).get_or_create(platform_code, platform_code.capitalize())
    if ProductRepository(db).get_by_external_id(platform.id, external_product_id):
        return
    ProductRepository(db).bulk_upsert_products(
        [
            {
                "platform_id": platform.id,
                "external_product_id": external_product_id,
                "title": title,
                "normalized_title": title.lower(),
                "description": "",
                "category": "unknown",
                "price": 0,
                "currency": "VND",
                "rating": 0,
                "review_count": 0,
                "sold_count": 0,
                "product_url": f"https://tiki.vn/product-p{external_product_id}.html",
            }
        ]
    )


def load_products_file(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise SystemExit("Products JSON phai la list object co product_id va spid.")
        return [normalize_product_row(item) for item in data]

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [normalize_product_row(row) for row in csv.DictReader(file)]


def normalize_product_row(row: dict[str, Any]) -> dict[str, str]:
    product_id = row.get("product_id") or row.get("productId") or row.get("id")
    spid = row.get("spid") or row.get("seller_product_id") or row.get("sellerProductId") or product_id
    if not product_id:
        raise SystemExit("Moi dong san pham can co product_id.")
    return {"product_id": str(product_id), "spid": str(spid)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Tiki reviews by 5 star levels")
    parser.add_argument("--product-id", default=DEFAULT_PRODUCT_ID, help="Tiki product_id")
    parser.add_argument("--spid", default=DEFAULT_SPID, help="Tiki spid")
    parser.add_argument("--products-file", help="CSV/JSON nhieu san pham. Cot: product_id,spid")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--max-pages-per-star", type=int, default=DEFAULT_MAX_PAGES_PER_STAR)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--import-to-mongo", action=argparse.BooleanOptionalAction, default=DEFAULT_IMPORT_TO_MONGO)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.products_file:
        products = load_products_file(Path(args.products_file))
    else:
        products = [{"product_id": str(args.product_id), "spid": str(args.spid)}]

    ensure_indexes(db)
    total_reviews = 0

    for product in products:
        product_id = product["product_id"]
        spid = product["spid"]
        reviews = fetch_all_reviews_by_stars(
            product_id=product_id,
            spid=spid,
            page_size=args.page_size,
            max_pages_per_star=args.max_pages_per_star,
            delay=args.delay,
        )

        raw_path = OUTPUT_DIR / f"all_stratified_reviews_{product_id}.json"
        normalized_path = OUTPUT_DIR / f"all_stratified_reviews_{product_id}_normalized.json"

        save_json(reviews, raw_path)
        normalized = normalize_tiki_reviews(reviews, external_product_id=product_id)
        save_json(normalized, normalized_path)
        total_reviews += len(reviews)

        if args.import_to_mongo:
            ensure_minimal_product(product_id, "tiki", f"Tiki product {product_id}")
            stats = JSONImporter(db).import_reviews_file(str(normalized_path), platform_code="tiki")
            print({"imported_to_mongo": True, **stats})

    print({"products_done": len(products), "total_source_reviews": total_reviews})


if __name__ == "__main__":
    main()
