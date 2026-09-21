import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import requests
from pymongo.database import Database

from app.config import settings
from app.db.repositories.platform_repo import PlatformRepository


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
IMAGE_URL_RE = re.compile(
    r"(?:(?:https?:)?//|)(?:[^\"'\s<>]*?(?:tikicdn|lazcdn|slatic|tiktokcdn|ibyteimg|byteimg)[^\"'\s<>]*?\.(?:jpg|jpeg|png|webp)(?:_[^\"'\s<>]*)?)",
    re.IGNORECASE,
)


@dataclass
class ProductMetadata:
    title: str = ""
    description: str = ""
    product_images: list[str] | None = None


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


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
    return clean_text(match.group(1)) if match else ""


def description_from_html(page_html: str) -> str:
    return meta_content(page_html, "og:description") or meta_content(page_html, "description")


def normalize_image_url(raw_url: str) -> str:
    value = html.unescape(raw_url or "")
    value = value.replace("\\/", "/").replace("\\u002F", "/").strip()
    value = unquote(value)
    value = re.split(r"[\s\"'<>)]", value, maxsplit=1)[0]
    while value.startswith("https://https://"):
        value = value.replace("https://https://", "https://", 1)
    while value.startswith("http://https://"):
        value = value.replace("http://https://", "https://", 1)
    if value.startswith("//"):
        value = f"https:{value}"
    elif not value.startswith("http") and any(domain in value for domain in ("tikicdn", "lazcdn", "slatic", "tiktokcdn", "ibyteimg", "byteimg")):
        value = f"https://{value.lstrip('/')}"
    if not value.startswith(("http://", "https://")):
        return ""
    clean_path = value.split("?", 1)[0].lower()
    if not clean_path.endswith(IMAGE_EXTENSIONS):
        return ""
    return value


def image_priority(url: str, platform_code: str) -> tuple[int, str]:
    score = 100
    lowered = url.lower()
    if platform_code == "tiki":
        if "tikicdn.com/cache" in lowered:
            score += 25
        if "media/catalog/product" in lowered or "/ts/product/" in lowered:
            score -= 40
    if platform_code == "lazada":
        if "img.lazcdn.com" in lowered:
            score -= 40
        if "slatic.net/p/" in lowered or "/p/" in lowered:
            score -= 30
    if platform_code == "tiktok_shop":
        if "ibyteimg.com" in lowered or "tiktokcdn.com" in lowered:
            score -= 30
        if "avatar" in lowered:
            score += 50
    if any(size in lowered for size in ("720x720", "750x750", "1200x1200")):
        score -= 10
    if any(word in lowered for word in ("avatar", "icon", "logo", "sprite", "rating", "review")):
        score += 40
    return score, url


def extract_product_image_urls(page_html: str, platform_code: str, limit: int = 8) -> list[str]:
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

    urls.sort(key=lambda url: image_priority(url, platform_code))
    return urls[:limit]


def fetch_product_html(product_url: str, platform_code: str) -> str:
    user_agent = settings.TIKTOK_SHOP_USER_AGENT if platform_code == "tiktok_shop" else settings.LAZADA_MTOP_USER_AGENT
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if platform_code == "lazada" and settings.LAZADA_MTOP_COOKIE:
        headers["Cookie"] = settings.LAZADA_MTOP_COOKIE
    if platform_code == "tiktok_shop":
        headers["Referer"] = "https://shop.tiktok.com/"
        if settings.TIKTOK_SHOP_COOKIE:
            headers["Cookie"] = settings.TIKTOK_SHOP_COOKIE
        if settings.TIKTOK_SHOP_X_TTS_OEC_BSID:
            headers["X-Tts-Oec-Bsid"] = settings.TIKTOK_SHOP_X_TTS_OEC_BSID
    session = requests.Session()
    session.trust_env = False
    timeout = settings.TIKTOK_SHOP_TIMEOUT_SECONDS if platform_code == "tiktok_shop" else settings.LAZADA_MTOP_TIMEOUT_SECONDS
    response = session.get(product_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def fetch_product_metadata(product_url: str, platform_code: str, limit_images: int = 8) -> ProductMetadata:
    page_html = fetch_product_html(product_url, platform_code)
    return ProductMetadata(
        title=title_from_html(page_html),
        description=description_from_html(page_html),
        product_images=extract_product_image_urls(page_html, platform_code, limit=limit_images),
    )


def update_product_metadata_from_url(
    db: Database,
    platform_code: str,
    external_product_id: str,
    product_url: str,
    fetch_url: str | None = None,
    limit_images: int = 8,
) -> dict[str, Any]:
    metadata = fetch_product_metadata(fetch_url or product_url, platform_code, limit_images=limit_images)
    platform = PlatformRepository(db).get_or_create(platform_code, platform_code.capitalize())
    update: dict[str, Any] = {"product_url": product_url}
    if metadata.title:
        update["title"] = metadata.title
        update["normalized_title"] = metadata.title.lower()
    if metadata.description:
        update["description"] = metadata.description
    if metadata.product_images:
        update["product_images"] = metadata.product_images

    db.products.update_one(
        {"platform_id": platform.id, "external_product_id": str(external_product_id)},
        {"$set": update},
    )
    return {
        "title": metadata.title,
        "description": metadata.description,
        "product_images": metadata.product_images or [],
        "images_found": len(metadata.product_images or []),
    }
