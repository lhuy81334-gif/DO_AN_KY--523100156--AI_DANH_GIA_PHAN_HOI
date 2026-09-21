import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional


class DataNormalizer:
    @staticmethod
    def clean_text(text: Optional[str]) -> str:
        if not text:
            return ""
        cleaned = re.sub(r"\s+", " ", text.strip())
        return cleaned

    @staticmethod
    def normalize_title(title: str) -> str:
        if not title:
            return ""
        clean = re.sub(r"[^\w\s-]", "", title.lower())
        return re.sub(r"\s+", " ", clean).strip()

    @staticmethod
    def normalize_datetime(value: Any) -> Optional[datetime]:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            relative_match = re.fullmatch(r"(\d+)\s+(day|days|week|weeks|month|months|year|years)\s+ago", text.lower())
            if relative_match:
                amount = int(relative_match.group(1))
                unit = relative_match.group(2)
                days = amount
                if unit.startswith("week"):
                    days = amount * 7
                elif unit.startswith("month"):
                    days = amount * 30
                elif unit.startswith("year"):
                    days = amount * 365
                return datetime.now(timezone.utc) - timedelta(days=days)
            if text.isdigit():
                timestamp = float(text)
                if timestamp > 10_000_000_000:
                    timestamp = timestamp / 1000
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    @staticmethod
    def normalize_product(raw: Dict[str, Any], platform_id: int, shop_id: Optional[int] = None) -> Dict[str, Any]:
        title = DataNormalizer.clean_text(str(raw.get("title", "")))
        normalized_title = DataNormalizer.normalize_title(title)

        try:
            price = float(raw.get("price", 0.0))
        except (ValueError, TypeError):
            price = 0.0

        try:
            rating = float(raw.get("rating", 0.0))
        except (ValueError, TypeError):
            rating = 0.0

        try:
            review_count = int(raw.get("review_count", 0))
        except (ValueError, TypeError):
            review_count = 0

        try:
            sold_count = int(raw.get("sold_count", 0))
        except (ValueError, TypeError):
            sold_count = 0

        external_id = str(raw.get("external_product_id") or raw.get("id") or raw.get("product_id") or "")

        return {
            "platform_id": platform_id,
            "shop_id": shop_id,
            "external_product_id": external_id,
            "title": title,
            "normalized_title": normalized_title,
            "description": DataNormalizer.clean_text(str(raw.get("description", ""))),
            "category": DataNormalizer.clean_text(str(raw.get("category", "T-Shirts"))),
            "price": price,
            "currency": str(raw.get("currency", "USD")),
            "rating": rating,
            "review_count": review_count,
            "sold_count": sold_count,
            "product_url": str(raw.get("product_url", "")),
        }

    @staticmethod
    def normalize_review(raw: Dict[str, Any], product_id: int) -> Dict[str, Any]:
        try:
            rating = float(raw.get("rating", 5.0))
        except (ValueError, TypeError):
            rating = 5.0

        try:
            likes = int(raw.get("review_like_count", 0) or raw.get("likes", 0))
        except (ValueError, TypeError):
            likes = 0

        external_id = str(raw.get("external_review_id") or raw.get("id") or raw.get("review_id") or "")

        source_created_at = DataNormalizer.normalize_datetime(raw.get("created_at") or raw.get("raw_created_at"))
        normalized = {
            "product_id": product_id,
            "external_review_id": external_id,
            "rating": rating,
            "review_text": DataNormalizer.clean_text(str(raw.get("review_text") or raw.get("comment") or raw.get("content") or "")),
            "review_language": str(raw.get("review_language", "en")),
            "review_like_count": likes,
        }
        if source_created_at:
            normalized["created_at"] = source_created_at
            normalized["raw_created_at"] = raw.get("created_at") or raw.get("raw_created_at")
        for optional_key in [
            "source",
            "platform_id",
            "platform_code",
            "external_product_id",
            "product_title",
            "sample_type",
            "raw_created_at",
            "images",
            "review_images",
            "image_urls",
            "sku_info",
            "spid",
            "verified_purchase",
            "is_verified_purchase",
            "image_relevance_score",
        ]:
            if raw.get(optional_key) is not None:
                normalized[optional_key] = raw[optional_key]
        return normalized
