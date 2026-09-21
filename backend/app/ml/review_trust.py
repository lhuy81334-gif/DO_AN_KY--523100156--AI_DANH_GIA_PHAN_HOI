import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.ml.sentiment import analyze_text_sentiment, extract_aspect_sentiments

GENERIC_REVIEW_TEXTS = {
    "ok",
    "good",
    "nice",
    "tot",
    "rat tot",
    "hai long",
    "rat hai long",
    "cuc ki hai long",
    "khong hai long",
}


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def rating_to_sentiment_score(rating: Optional[float]) -> float:
    if rating is None:
        return 0.0
    if rating >= 4.5:
        return 1.0
    if rating >= 3.5:
        return 0.5
    if rating >= 2.5:
        return 0.0
    if rating >= 1.5:
        return -0.5
    return -1.0


def label_from_score(score: float) -> str:
    if score >= 0.25:
        return "positive"
    if score <= -0.25:
        return "negative"
    return "neutral"


def text_sentiment_score(text: str) -> Tuple[str, float]:
    label, confidence = analyze_text_sentiment(strip_accents(text))
    if label == "positive":
        return label, confidence
    if label == "negative":
        return label, -confidence
    return label, 0.0


def content_specificity_score(text: str) -> float:
    clean = strip_accents(text)
    words = re.findall(r"\w+", clean)
    if not words:
        return 0.0

    aspect_count = len(extract_aspect_sentiments(clean))
    length_score = min(45.0, len(words) * 3.0)
    aspect_score = min(35.0, aspect_count * 17.5)
    detail_score = 20.0 if re.search(r"\d|size|mau|vai|giao|dong goi|rach|mop|meo|in|chat lieu", clean) else 0.0
    penalty = 25.0 if clean.strip() in GENERIC_REVIEW_TEXTS or len(words) <= 3 else 0.0
    return clamp(length_score + aspect_score + detail_score - penalty)


def review_images(review: Dict[str, Any]) -> List[Any]:
    for key in ("review_images", "image_urls", "images", "media"):
        value = review.get(key)
        if isinstance(value, list):
            return value
        if value:
            return [value]
    return []


def average_numeric(values: Iterable[Any]) -> Optional[float]:
    nums = []
    for value in values:
        try:
            nums.append(float(value))
        except (TypeError, ValueError):
            continue
    if not nums:
        return None
    return sum(nums) / len(nums)


def image_evidence_score(review: Dict[str, Any]) -> Tuple[float, str]:
    direct_score = review.get("image_relevance_score")
    if direct_score is not None:
        return clamp(float(direct_score)), str(review.get("image_evidence_status") or "scored_by_vision_model")

    images = review_images(review)
    if not images:
        return 50.0, "no_review_image"

    per_image_scores = []
    for image in images:
        if isinstance(image, dict):
            per_image_scores.extend(
                image.get(key)
                for key in ("relevance_score", "product_match_score", "image_relevance_score")
                if image.get(key) is not None
            )
    avg = average_numeric(per_image_scores)
    if avg is not None:
        return clamp(avg), "scored_from_image_metadata"

    return 55.0, "image_present_not_verified"


def purchase_score(review: Dict[str, Any]) -> float:
    value = review.get("verified_purchase")
    if value is None:
        value = review.get("is_verified_purchase")
    if value is None:
        value = review.get("purchased")
    if value is True:
        return 100.0
    if value is False:
        return 20.0
    return 50.0


def sku_match_score(review: Dict[str, Any]) -> float:
    if review.get("sku_match_score") is not None:
        return clamp(float(review["sku_match_score"]))
    if review.get("sku_info") or review.get("spid"):
        return 70.0
    return 50.0


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def trust_level(score: float) -> str:
    if score >= 80:
        return "strong"
    if score >= 60:
        return "good"
    if score >= 40:
        return "medium"
    if score >= 20:
        return "weak"
    return "very_weak"


def analyze_review_trust(review: Dict[str, Any]) -> Dict[str, Any]:
    text = str(review.get("review_text") or review.get("content") or review.get("comment") or "")
    rating = review.get("rating")
    try:
        rating_float = float(rating)
    except (TypeError, ValueError):
        rating_float = None

    rating_score = rating_to_sentiment_score(rating_float)
    rating_label = label_from_score(rating_score)
    text_label, text_score = text_sentiment_score(text)
    aspects = extract_aspect_sentiments(strip_accents(text))
    negative_aspects = [item["aspect"] for item in aspects if item.get("sentiment") == "negative"]
    positive_aspects = [item["aspect"] for item in aspects if item.get("sentiment") == "positive"]

    has_text = bool(strip_accents(text).strip())
    has_images = bool(review_images(review))
    specificity = content_specificity_score(text)
    image_score, image_status = image_evidence_score(review)
    purchase = purchase_score(review)
    sku = sku_match_score(review)

    sentiment_gap = abs(rating_score - text_score)
    flags = []
    if not has_text:
        flags.append("rating_only_review")
    if rating_float is not None and rating_float >= 4 and negative_aspects:
        flags.append("high_rating_with_complaint")
    if rating_float is not None and rating_float <= 2 and not negative_aspects and specificity < 35:
        flags.append("low_rating_without_clear_reason")
    if sentiment_gap >= 0.75 and has_text:
        flags.append("rating_text_mismatch")
    if has_images and image_score < 40:
        flags.append("image_may_not_match_product")
    if has_images and review.get("claim_evidence_status") == "claim_evidence_mismatch_risk":
        flags.append("image_does_not_support_review_claim")
    if rating_float is not None and rating_float <= 2 and review.get("claim_evidence_status") == "claim_evidence_mismatch_risk":
        flags.append("negative_review_image_does_not_support_claim")
    if has_images and image_score < 40 and specificity < 40:
        flags.append("weak_text_and_weak_image_evidence")

    anomaly_penalty = 0.0
    anomaly_penalty += 18.0 if "rating_text_mismatch" in flags else 0.0
    anomaly_penalty += 22.0 if "image_may_not_match_product" in flags else 0.0
    anomaly_penalty += 18.0 if "image_does_not_support_review_claim" in flags else 0.0
    anomaly_penalty += 12.0 if "rating_only_review" in flags else 0.0
    anomaly_penalty += 10.0 if "low_rating_without_clear_reason" in flags else 0.0
    anomaly_score = clamp(100.0 - anomaly_penalty)

    final_score = (
        0.30 * image_score
        + 0.25 * specificity
        + 0.20 * purchase
        + 0.15 * sku
        + 0.10 * anomaly_score
    )

    use_for_text_analysis = has_text and specificity >= 20
    use_as_strong_evidence = final_score >= 70 and specificity >= 45 and (not has_images or image_score >= 60)

    return {
        "rating_sentiment": rating_label,
        "rating_sentiment_score": round(rating_score, 3),
        "text_sentiment": text_label,
        "text_sentiment_score": round(text_score, 3),
        "sentiment_gap": round(sentiment_gap, 3),
        "has_text": has_text,
        "has_images": has_images,
        "positive_aspects": positive_aspects,
        "negative_aspects": negative_aspects,
        "content_specificity_score": round(specificity, 2),
        "image_evidence_score": round(image_score, 2),
        "image_evidence_status": image_status,
        "purchase_score": round(purchase, 2),
        "sku_match_score": round(sku, 2),
        "review_trust_score": round(clamp(final_score), 2),
        "trust_level": trust_level(final_score),
        "use_for_rating_stats": rating_float is not None,
        "use_for_text_analysis": use_for_text_analysis,
        "use_as_strong_evidence": use_as_strong_evidence,
        "flags": flags,
    }
