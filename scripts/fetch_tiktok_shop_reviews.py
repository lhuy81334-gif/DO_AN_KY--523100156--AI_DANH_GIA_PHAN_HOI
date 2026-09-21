import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from datetime import datetime

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR / "backend"))

from app.config import settings
from app.db.database import db, ensure_indexes
from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.product_repo import ProductRepository
from app.ingestion.json_importer import JSONImporter


TIKTOK_REVIEW_URL = "https://shop.tiktok.com/api/shop/pdp_desktop/get_product_reviews"
OUTPUT_DIR = ROOT_DIR / "data/api/tiktok_shop"
DEFAULT_PRODUCT_ID = "1730279169693551229"
DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_PAGES_PER_STAR = 20
DEFAULT_DELAY = 1.0
DEFAULT_IMPORT_TO_MONGO = True
IMAGE_FIELD_MARKERS = ("image", "img", "pic", "photo", "media", "cover", "url")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def review_timestamp(review: dict[str, Any]) -> float:
    value = review.get("review_time")
    if value is None or value == "":
        return 0.0
    try:
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return timestamp
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0


def build_session(referer: str = "") -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    headers = {
        "User-Agent": settings.TIKTOK_SHOP_USER_AGENT,
        "Accept": "application/json,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://shop.tiktok.com",
        "Referer": referer or "https://shop.tiktok.com/",
        "Content-Type": "application/json",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Priority": "u=0",
        "Connection": "keep-alive",
    }
    if settings.TIKTOK_SHOP_COOKIE:
        headers["Cookie"] = settings.TIKTOK_SHOP_COOKIE
    session.headers.update(headers)
    return session


def review_url() -> str:
    if settings.TIKTOK_SHOP_X_TTS_OEC_BSID:
        return f"{TIKTOK_REVIEW_URL}?{urlencode({'X-Tts-Oec-Bsid': settings.TIKTOK_SHOP_X_TTS_OEC_BSID})}"
    return TIKTOK_REVIEW_URL


def validate_tiktok_config(product_id: str) -> None:
    if not product_id or product_id.upper().startswith("ID_SAN_PHAM"):
        raise RuntimeError("Hay truyen TikTok Shop product_id that.")
    for label, value in {
        "TIKTOK_SHOP_COOKIE": settings.TIKTOK_SHOP_COOKIE,
        "TIKTOK_SHOP_X_TTS_OEC_BSID": settings.TIKTOK_SHOP_X_TTS_OEC_BSID,
    }.items():
        if "..." in value or "…" in value:
            raise RuntimeError(f"{label} bi rut gon bang .../…. Hay copy full header tu DevTools.")
        try:
            value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise RuntimeError(f"{label} co ky tu la. Hay copy lai raw header tu browser.") from exc


def fetch_reviews_by_stars(
    product_id: str,
    page_size: int = 20,
    max_pages_per_star: int = 20,
    delay: float = 1.0,
    referer: str = "",
) -> list[dict[str, Any]]:
    validate_tiktok_config(product_id)
    session = build_session(referer=referer)
    all_reviews: list[dict[str, Any]] = []

    print(f"Bat dau thu thap review TikTok Shop cho san pham {product_id}...")
    for star in [5, 4, 3, 2, 1]:
        print(f"\n--- Dang vet danh gia {star} sao ---")
        star_count = 0

        for page in range(1, max_pages_per_star + 1):
            payload = {
                "component_name": "pdp_left_reviews",
                "page_size": page_size,
                "page_start": page,
                "product_id": str(product_id),
                "review_filter": {"filter_type": 1, "filter_value": star},
                "sort_rule": 1,
            }
            print(f"  [>] payload page_start={page}, filter_value={star}, page_size={page_size}")

            try:
                response = session.post(
                    review_url(),
                    json=payload,
                    timeout=settings.TIKTOK_SHOP_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                response_json = response.json()
                if str(response_json.get("code", 0)) != "0":
                    message = response_json.get("message") or response_json
                    print(f"  [!] TikTok dung o {star} sao - Trang {page}: {message}")
                    if not all_reviews and star_count == 0:
                        raise RuntimeError(f"TikTok Shop API error: {message}")
                    print("  [i] Giu lai review da gom va chuyen sang muc sao tiep theo.")
                    break

                data = response_json.get("data") or {}
                reviews = data.get("product_reviews") or []
                if not reviews:
                    print(f"  [i] Da het review cho muc {star} sao.")
                    break

                sample_label = "HIGH_RATING" if star >= 4 else "LOW_RATING"
                if star == 3:
                    sample_label = "NEUTRAL_RATING"

                for review in reviews:
                    review["sample_type"] = sample_label
                    all_reviews.append(review)

                star_count += len(reviews)
                print(f"  [+] {star} sao - Trang {page}: nhan {len(reviews)} review (Luy ke: {star_count})")

                if not data.get("has_more"):
                    break

                if delay > 0:
                    time.sleep(delay)
            except requests.exceptions.RequestException as exc:
                print(f"  [x] Loi mang tai trang {page}: {exc}")
                break

    print("\n" + "=" * 50)
    all_reviews.sort(key=review_timestamp, reverse=True)
    print(f"Tong ket: Da gom duoc {len(all_reviews)} review TikTok Shop tren toan bo 5 dai sao.")
    return all_reviews


def extract_tiktok_image_urls(review: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def add_url(value: str) -> None:
        clean = value.strip().replace("\\/", "/")
        if clean.startswith("//"):
            clean = f"https:{clean}"
        clean_path = clean.split("?", 1)[0].lower()
        if clean.startswith("http") and clean_path.endswith(IMAGE_EXTENSIONS) and clean not in seen:
            seen.add(clean)
            urls.append(clean)

    def walk(value: Any, parent_key: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                next_parent = f"{parent_key}.{str(key).lower()}" if parent_key else str(key).lower()
                walk(child, next_parent)
            return
        if isinstance(value, list):
            for child in value:
                walk(child, parent_key)
            return
        if not isinstance(value, str):
            return
        if any(marker in parent_key for marker in IMAGE_FIELD_MARKERS) or value.split("?", 1)[0].lower().endswith(IMAGE_EXTENSIONS):
            add_url(value)

    for key in ("display_image_url", "review_images", "images", "media", "review_media"):
        if key in review:
            walk(review[key], key)
    return urls


def normalize_tiktok_reviews(reviews: list[dict[str, Any]], external_product_id: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for review in reviews:
        text = str(review.get("review_text") or "").strip()
        if not text:
            continue
        image_urls = extract_tiktok_image_urls(review)
        normalized.append(
            {
                "external_product_id": external_product_id,
                "external_review_id": str(review.get("review_id") or ""),
                "source": "TIKTOK_SHOP",
                "platform_code": "tiktok_shop",
                "rating": float(review.get("review_rating") or 5),
                "review_text": text,
                "review_language": "vi",
                "review_like_count": int(review.get("like_count") or review.get("helpful_count") or 0),
                "sample_type": review.get("sample_type", ""),
                "raw_created_at": review.get("review_time"),
                "sku_info": str(review.get("sku_id") or ""),
                "verified_purchase": review.get("is_verified_purchase"),
                "is_incentivized_review": review.get("is_incentivized_review"),
                "reviewer_name": review.get("reviewer_name"),
                "product_title": review.get("product_name", ""),
                "images": [{"full_path": url, "status": "approved"} for url in image_urls],
                "image_urls": image_urls,
            }
        )
    return normalized


def save_json(data: Any, filename: Path) -> None:
    filename.parent.mkdir(parents=True, exist_ok=True)
    with filename.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    print(f"Da luu vao: {filename}")


def ensure_minimal_product(external_product_id: str, platform_code: str, title: str, product_url: str = "") -> None:
    platform = PlatformRepository(db).get_or_create(platform_code, "TikTok Shop")
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
                "product_url": product_url or f"https://shop.tiktok.com/vn/pdp/{external_product_id}",
            }
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch TikTok Shop reviews by 5 star levels")
    parser.add_argument("--product-id", default=DEFAULT_PRODUCT_ID, help="TikTok Shop product_id")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--max-pages-per-star", type=int, default=DEFAULT_MAX_PAGES_PER_STAR)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--referer", default="", help="TikTok Shop PDP URL copied from browser")
    parser.add_argument("--import-to-mongo", action=argparse.BooleanOptionalAction, default=DEFAULT_IMPORT_TO_MONGO)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_indexes(db)

    product_id = str(args.product_id)
    reviews = fetch_reviews_by_stars(
        product_id=product_id,
        page_size=args.page_size,
        max_pages_per_star=args.max_pages_per_star,
        delay=args.delay,
        referer=args.referer,
    )

    raw_path = OUTPUT_DIR / f"all_tiktok_shop_reviews_{product_id}.json"
    normalized_path = OUTPUT_DIR / f"all_tiktok_shop_reviews_{product_id}_normalized.json"
    save_json(reviews, raw_path)
    normalized = normalize_tiktok_reviews(reviews, external_product_id=product_id)
    save_json(normalized, normalized_path)
    print({"source_reviews": len(reviews), "normalized_reviews": len(normalized), "database": db.name})

    if args.import_to_mongo:
        title = normalized[0].get("product_title") if normalized else f"TikTok Shop product {product_id}"
        ensure_minimal_product(product_id, "tiktok_shop", str(title or f"TikTok Shop product {product_id}"), args.referer)
        stats = JSONImporter(db).import_reviews_file(str(normalized_path), platform_code="tiktok_shop")
        print({"imported_to_mongo": True, **stats})


if __name__ == "__main__":
    main()
