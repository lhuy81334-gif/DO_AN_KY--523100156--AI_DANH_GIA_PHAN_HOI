import argparse
import html
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR / "backend"))

from app.config import settings
from app.db.database import db, ensure_indexes
from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.product_repo import ProductRepository


DEFAULT_EXTERNAL_PRODUCT_ID = "310626559"
DEFAULT_LIMIT_IMAGES = 8
LAZADA_PRODUCT_URL_TEMPLATE = "https://www.lazada.vn/products/i{external_product_id}.html"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
IMAGE_URL_RE = re.compile(
    r"(?:(?:https?:)?//|)(?:[^\"'\s<>]*?(?:lazcdn|slatic)[^\"'\s<>]*?\.(?:jpg|jpeg|png|webp)(?:_[^\"'\s<>]*)?)",
    re.IGNORECASE,
)


def fetch_html(product_url: str) -> str:
    headers = {
        "User-Agent": settings.LAZADA_MTOP_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    response = requests.get(product_url, headers=headers, timeout=settings.LAZADA_MTOP_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return html.unescape(value).strip()


def meta_content(page_html: str, key: str) -> str:
    patterns = [
        rf"<meta[^>]+(?:property|name)=[\"']{re.escape(key)}[\"'][^>]+content=[\"']([^\"']+)[\"']",
        rf"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:property|name)=[\"']{re.escape(key)}[\"']",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_html, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(1))
    return ""


def title_from_html(page_html: str) -> str:
    title = meta_content(page_html, "og:title")
    if title:
        return title
    match = re.search(r"<title[^>]*>(.*?)</title>", page_html, flags=re.IGNORECASE | re.DOTALL)
    return clean_text(re.sub(r"\s+", " ", match.group(1))) if match else ""


def description_from_html(page_html: str) -> str:
    return meta_content(page_html, "og:description") or meta_content(page_html, "description")


def normalize_image_url(raw_url: str) -> str:
    value = html.unescape(raw_url)
    value = value.replace("\\/", "/").replace("\\u002F", "/").strip()
    value = unquote(value)
    value = re.split(r"[\s\"'<>)]", value, maxsplit=1)[0]
    while value.startswith("https://https://"):
        value = value.replace("https://https://", "https://", 1)
    while value.startswith("http://https://"):
        value = value.replace("http://https://", "https://", 1)
    if value.startswith("//"):
        value = f"https:{value}"
    elif not value.startswith("http") and (value.startswith("img.") or "lazcdn" in value or "slatic" in value):
        value = f"https://{value.lstrip('/')}"
    if not value.startswith("http"):
        return ""
    clean_path = value.split("?", 1)[0].lower()
    if not clean_path.endswith(IMAGE_EXTENSIONS):
        return ""
    return value


def image_priority(url: str) -> tuple[int, str]:
    score = 100
    lowered = url.lower()
    if "img.lazcdn.com" in lowered:
        score -= 40
    if "slatic.net/p/" in lowered or "/p/" in lowered:
        score -= 30
    if "720x720" in lowered:
        score -= 10
    if any(word in lowered for word in ["avatar", "icon", "logo", "sprite", "rating", "review"]):
        score += 30
    return score, url


def extract_product_image_urls(page_html: str, limit: int = DEFAULT_LIMIT_IMAGES) -> list[str]:
    normalized_html = page_html.replace("\\/", "/").replace("\\u002F", "/")
    candidates = [meta_content(page_html, "og:image")]
    candidates.extend(match.group(0) for match in IMAGE_URL_RE.finditer(normalized_html))

    seen: set[str] = set()
    urls: list[str] = []
    for candidate in candidates:
        url = normalize_image_url(candidate)
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)

    urls.sort(key=image_priority)
    return urls[:limit]


def product_payload(
    platform_id: int,
    external_product_id: str,
    product_url: str,
    title: str,
    description: str,
    category: str,
    image_urls: list[str],
) -> dict[str, Any]:
    safe_title = title or f"Lazada product {external_product_id}"
    return {
        "platform_id": platform_id,
        "external_product_id": external_product_id,
        "title": safe_title,
        "normalized_title": safe_title.lower(),
        "description": description,
        "category": category or "unknown",
        "product_url": product_url,
        "product_images": image_urls,
        "source": "LAZADA",
    }


def update_product(args: argparse.Namespace) -> None:
    ensure_indexes(db)
    external_product_id = str(args.external_product_id)
    product_url = args.product_url or LAZADA_PRODUCT_URL_TEMPLATE.format(external_product_id=external_product_id)

    if args.html_file:
        page_html = Path(args.html_file).read_text(encoding="utf-8")
    else:
        page_html = fetch_html(product_url)

    image_urls = list(args.image_url or [])
    image_urls.extend(extract_product_image_urls(page_html, limit=args.limit_images))
    image_urls = list(dict.fromkeys(url for url in image_urls if normalize_image_url(url)))[: args.limit_images]

    title = args.title or title_from_html(page_html)
    description = args.description or description_from_html(page_html)
    category = args.category or "unknown"

    platform = PlatformRepository(db).get_or_create("lazada", "Lazada")
    repo = ProductRepository(db)
    existing = repo.get_by_external_id(platform.id, external_product_id)
    payload = product_payload(platform.id, external_product_id, product_url, title, description, category, image_urls)
    stats = repo.bulk_upsert_products([payload])
    product = repo.get_by_external_id(platform.id, external_product_id)

    print({
        "database": db.name,
        "collection": "products",
        "product_id": product.id if product else None,
        "external_product_id": external_product_id,
        "was_existing": bool(existing),
        "images_found": len(image_urls),
        **stats,
    })
    for index, url in enumerate(image_urls, start=1):
        print(f"{index}. {url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Lazada product title and product_images in MongoDB")
    parser.add_argument("--external-product-id", default=DEFAULT_EXTERNAL_PRODUCT_ID, help="Lazada item id, for example 310626559")
    parser.add_argument("--product-url", help="Full Lazada product URL")
    parser.add_argument("--html-file", help="Saved Lazada product HTML if direct fetch is blocked")
    parser.add_argument("--title", help="Override product title")
    parser.add_argument("--description", help="Override product description")
    parser.add_argument("--category", help="Override product category")
    parser.add_argument("--image-url", action="append", help="Add a product image URL manually; can be used multiple times")
    parser.add_argument("--limit-images", type=int, default=DEFAULT_LIMIT_IMAGES)
    return parser.parse_args()


if __name__ == "__main__":
    update_product(parse_args())
