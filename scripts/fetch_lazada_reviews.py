import argparse
import hashlib
import json
import os
import sys
import time
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from datetime import datetime

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR / "backend"))

from app.config import settings
from app.db.database import db, ensure_indexes
from app.ingestion.json_importer import JSONImporter
from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.product_repo import ProductRepository


APP_KEY = "24677475"
API_NAME = "mtop.lazada.review.item.getPcReviewList"
LAZADA_REVIEW_URL = "https://acs-m.lazada.vn/h5/mtop.lazada.review.item.getpcreviewlist/1.0/"
OUTPUT_DIR = ROOT_DIR / "data/api/lazada"
DEFAULT_ITEM_ID = "310626559"
DEFAULT_PAGE_SIZE = 5
DEFAULT_MAX_PAGES_PER_STAR = 20
DEFAULT_DELAY = 2.0
DEFAULT_IMPORT_TO_MONGO = True
IMAGE_FIELD_MARKERS = ("image", "img", "pic", "photo", "media", "video", "url")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")


def review_timestamp(review: dict[str, Any]) -> float:
    value = review.get("created_at")
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


def is_user_validate_error(exc: Exception) -> bool:
    return "FAIL_SYS_USER_VALIDATE" in str(exc)


def build_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    headers = {
        "User-Agent": settings.LAZADA_MTOP_USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://www.lazada.vn",
        "Referer": "https://www.lazada.vn/",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if settings.LAZADA_MTOP_X_UA:
        headers["x-ua"] = settings.LAZADA_MTOP_X_UA
    if settings.LAZADA_MTOP_X_UMIDTOKEN:
        headers["x-umidtoken"] = settings.LAZADA_MTOP_X_UMIDTOKEN
    if settings.LAZADA_MTOP_COOKIE:
        load_cookie_header(session, settings.LAZADA_MTOP_COOKIE)
    session.headers.update(headers)
    return session


def load_cookie_header(session: requests.Session, cookie_header: str) -> None:
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    for key, morsel in cookie.items():
        session.cookies.set(key, morsel.value, domain=".lazada.vn")


def get_token(session: requests.Session) -> str | None:
    cookie_tk = find_cookie_value(session, "_m_h5_tk")
    if not cookie_tk:
        session.get(LAZADA_REVIEW_URL, timeout=10)
        cookie_tk = find_cookie_value(session, "_m_h5_tk")
    return cookie_tk.split("_", 1)[0] if cookie_tk else None


def find_cookie_value(session: requests.Session, name: str) -> str | None:
    for cookie in session.cookies:
        if cookie.name == name:
            return cookie.value
    return None


def clear_mtop_token(session: requests.Session) -> None:
    for cookie in list(session.cookies):
        if cookie.name in {"_m_h5_tk", "_m_h5_tk_enc"}:
            session.cookies.clear(cookie.domain, cookie.path, cookie.name)


def fetch_all_lazada_reviews(
    item_id: str,
    page_size: int = 5,
    max_pages_per_star: int = 20,
    delay: float = 2.0,
    tag_id: int = 0,
    stars_order: list[int] | None = None,
) -> dict[str, Any]:
    validate_lazada_config(item_id)
    session = build_session()
    all_collected: list[dict[str, Any]] = []
    market_stats: list[dict[str, Any]] = []
    stars_list = stars_order or [5, 4, 3, 2, 1]
    stop_all = False
    stopped_by_validate = False
    last_error = ""

    for star in stars_list:
        if stop_all:
            break
        print(f"\n--- Dang vet danh gia {star} sao ---")
        page = 1

        while page <= max_pages_per_star:
            token = get_token(session)
            if not token:
                print("[!] Khong lay duoc token tu cookie.")
                break

            payload_dict = {
                "itemId": item_id,
                "pageSize": page_size,
                "pageNo": page,
                "ratingFilter": star,
                "sort": 0,
                "tagId": tag_id,
            }
            data_str = json.dumps(payload_dict, separators=(",", ":"))
            timestamp_ms = str(int(time.time() * 1000))
            base_str = f"{token}&{timestamp_ms}&{APP_KEY}&{data_str}"
            sign = hashlib.md5(base_str.encode("utf-8")).hexdigest()

            params = {
                "jsv": "2.7.2",
                "appKey": APP_KEY,
                "t": timestamp_ms,
                "sign": sign,
                "api": API_NAME,
                "v": "1.0",
                "type": "originaljson",
                "isSec": "1",
                "AntiCreep": "true",
                "timeout": "10000",
                "dataType": "json",
                "sessionOption": "AutoLoginOnly",
                "x-i18n-language": "en",
                "x-i18n-regionID": "VN",
                "data": data_str,
            }

            try:
                response_json = post_lazada_with_retry(session, params)
                module = response_json.get("data", {}).get("module", {})

                if not market_stats and "impressionTags" in module:
                    market_stats = module.get("impressionTags", [])

                reviews = module.get("reviews", [])
                if not reviews:
                    print(f"  [i] Da het review cho muc {star} sao.")
                    break

                sample_label = "HIGH_RATING" if star >= 4 else "LOW_RATING"
                if star == 3:
                    sample_label = "NEUTRAL_RATING"

                for review in reviews:
                    all_collected.append(normalize_lazada_review(review, item_id, sample_label))

                print(f"  [+] {star} sao - Trang {page}: nhan {len(reviews)} review (Luy ke: {len(all_collected)})")
                page += 1
                if delay > 0:
                    time.sleep(delay)

            except Exception as exc:
                last_error = safe_error_text(exc)
                print(f"  [!] Loi tai trang {page}: {last_error}")
                if is_user_validate_error(exc):
                    print("  [!] Lazada da yeu cau xac minh/chong bot. Dung vet cac muc sao con lai de giu du lieu da gom.")
                    stopped_by_validate = True
                    stop_all = True
                break

    all_collected.sort(key=review_timestamp, reverse=True)
    output_data = {
        "market_statistics": market_stats,
        "collected_count": len(all_collected),
        "reviews": all_collected,
        "stopped_by_validate": stopped_by_validate,
        "last_error": last_error,
    }
    print("\n" + "=" * 45)
    print(f"Hoan tat! Tong cong thu duoc {len(all_collected)} review tren 5 dai sao.")
    return output_data


def normalize_lazada_review(review: dict[str, Any], item_id: str, sample_type: str) -> dict[str, Any]:
    contents = review.get("reviewContentList", [])
    text = contents[0].get("content") if contents and isinstance(contents[0], dict) else ""
    if not text:
        text = str(review.get("reviewContent") or review.get("content") or "").strip()
    image_urls = extract_lazada_image_urls(review)
    return {
        "review_id": review.get("reviewId"),
        "product_id": item_id,
        "rating": review.get("rating"),
        "review_text": text,
        "buyer_name": review.get("buyerName"),
        "likes": review.get("likeCount", 0),
        "created_at": review.get("reviewTime"),
        "sku_info": review.get("skuInfo"),
        "source": "LAZADA",
        "sample_type": sample_type,
        "images": [{"full_path": url, "status": "approved"} for url in image_urls],
        "image_urls": image_urls,
    }


def extract_lazada_image_urls(review: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def add_url(value: str) -> None:
        clean = value.strip()
        if clean.startswith("//"):
            clean = f"https:{clean}"
        clean_path = clean.split("?", 1)[0].lower()
        if clean_path.endswith(VIDEO_EXTENSIONS) or not clean_path.endswith(IMAGE_EXTENSIONS):
            return
        if clean.startswith("http") and clean not in seen:
            seen.add(clean)
            urls.append(clean)

    def walk(value: Any, parent_key: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key).lower()
                next_parent = f"{parent_key}.{key_text}" if parent_key else key_text
                walk(child, next_parent)
            return
        if isinstance(value, list):
            for child in value:
                walk(child, parent_key)
            return
        if not isinstance(value, str):
            return
        field_looks_visual = any(marker in parent_key for marker in IMAGE_FIELD_MARKERS)
        value_looks_visual = value.split("?", 1)[0].lower().endswith(IMAGE_EXTENSIONS)
        if field_looks_visual or value_looks_visual:
            add_url(value)

    for key in (
        "reviewImages",
        "reviewImageList",
        "reviewPicList",
        "reviewPics",
        "images",
        "imageList",
        "mediaList",
        "reviewMedias",
    ):
        if key in review:
            walk(review[key], key)
    walk(review)
    return urls


def to_import_schema(output_data: dict[str, Any], external_product_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, review in enumerate(output_data.get("reviews", []), start=1):
        text = str(review.get("review_text") or "").strip()
        if not text:
            continue
        review_id = review.get("review_id") or stable_review_id(external_product_id, text, index)
        rows.append(
            {
                "external_product_id": external_product_id,
                "external_review_id": str(review_id),
                "platform_code": "lazada",
                "source": "LAZADA",
                "rating": float(review.get("rating") or 5),
                "review_text": text,
                "review_language": "vi",
                "review_like_count": int(review.get("likes") or 0),
                "sample_type": review.get("sample_type", ""),
                "raw_created_at": review.get("created_at"),
                "sku_info": review.get("sku_info"),
                "images": review.get("images", []),
                "image_urls": review.get("image_urls", []),
            }
        )
    return rows


def validate_lazada_config(item_id: str) -> None:
    if item_id.upper().startswith("ID_SAN_PHAM") or item_id.upper() == "ID_THAT":
        raise RuntimeError("Hay thay --item-id bang Lazada itemId that.")
    if settings.LAZADA_MTOP_COOKIE and ("..." in settings.LAZADA_MTOP_COOKIE or "…" in settings.LAZADA_MTOP_COOKIE):
        raise RuntimeError("LAZADA_MTOP_COOKIE bi rut gon bang .../…. Hay copy lai full Cookie bang Copy as cURL.")
    for label, value in {
        "LAZADA_MTOP_COOKIE": settings.LAZADA_MTOP_COOKIE,
        "LAZADA_MTOP_X_UA": settings.LAZADA_MTOP_X_UA,
        "LAZADA_MTOP_X_UMIDTOKEN": settings.LAZADA_MTOP_X_UMIDTOKEN,
    }.items():
        try:
            value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise RuntimeError(f"{label} co ky tu la. Hay copy lai raw header tu browser.") from exc


def raise_for_lazada_error(payload: dict[str, Any]) -> None:
    ret = payload.get("ret")
    if isinstance(ret, list) and ret:
        code = str(ret[0])
        if not code.startswith("SUCCESS"):
            if "TOKEN" in code.upper() or "EXOIRED" in code.upper() or "EXPIRED" in code.upper():
                raise RuntimeError("LAZADA_TOKEN_EXPIRED")
            raise RuntimeError(f"Lazada MTOP error: {code}")


def post_lazada_with_retry(session: requests.Session, params: dict[str, Any]) -> dict[str, Any]:
    for attempt in [1, 2]:
        response = session.post(LAZADA_REVIEW_URL, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        try:
            raise_for_lazada_error(payload)
            return payload
        except RuntimeError as exc:
            if str(exc) != "LAZADA_TOKEN_EXPIRED" or attempt == 2:
                raise
            clear_mtop_token(session)
            session.get(LAZADA_REVIEW_URL, timeout=10)
            token = get_token(session)
            if not token:
                raise RuntimeError("Khong lay duoc token Lazada moi sau khi token cu het han.") from exc
            data_str = params["data"]
            timestamp_ms = str(int(time.time() * 1000))
            params["t"] = timestamp_ms
            params["sign"] = hashlib.md5(f"{token}&{timestamp_ms}&{APP_KEY}&{data_str}".encode("utf-8")).hexdigest()
    raise RuntimeError("Khong goi duoc Lazada API.")


def safe_error_text(exc: Exception) -> str:
    return str(exc).encode("ascii", errors="replace").decode("ascii")


def stable_review_id(product_id: str, text: str, index: int) -> str:
    digest = hashlib.sha1(f"{product_id}:{index}:{text}".encode("utf-8")).hexdigest()[:16]
    return f"lazada_{digest}"


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
                "product_url": f"https://www.lazada.vn/products/i{external_product_id}.html",
            }
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Lazada reviews by 5 star levels")
    parser.add_argument("--item-id", default=DEFAULT_ITEM_ID, help="Lazada itemId")
    parser.add_argument("--external-product-id", help="Product id stored in MongoDB products.external_product_id")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--max-pages-per-star", type=int, default=DEFAULT_MAX_PAGES_PER_STAR)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--tag-id", type=int, default=0, help="Lazada review tagId. Use -1 for With images/videos.")
    parser.add_argument("--with-images-only", action="store_true", help="Shortcut for Lazada tagId=-1.")
    parser.add_argument("--import-to-mongo", action=argparse.BooleanOptionalAction, default=DEFAULT_IMPORT_TO_MONGO)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_indexes(db)

    external_product_id = args.external_product_id or args.item_id
    output_data = fetch_all_lazada_reviews(
        item_id=str(args.item_id),
        page_size=args.page_size,
        max_pages_per_star=args.max_pages_per_star,
        delay=args.delay,
        tag_id=-1 if args.with_images_only else args.tag_id,
    )

    raw_path = OUTPUT_DIR / f"all_lazada_reviews_{external_product_id}.json"
    normalized_path = OUTPUT_DIR / f"all_lazada_reviews_{external_product_id}_normalized.json"
    save_json(output_data, raw_path)

    normalized = to_import_schema(output_data, external_product_id=external_product_id)
    save_json(normalized, normalized_path)
    print({"source_reviews": output_data["collected_count"], "normalized_reviews": len(normalized), "database": db.name})

    if args.import_to_mongo:
        ensure_minimal_product(external_product_id, "lazada", f"Lazada product {external_product_id}")
        stats = JSONImporter(db).import_reviews_file(str(normalized_path), platform_code="lazada")
        print({"imported_to_mongo": True, **stats})


if __name__ == "__main__":
    main()
