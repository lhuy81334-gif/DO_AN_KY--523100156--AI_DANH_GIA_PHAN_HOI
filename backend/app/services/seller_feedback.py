from collections import Counter
from typing import Any, Dict, List, Optional

from pymongo.database import Database

from app.ml.review_trust import analyze_review_trust


LOW_RATING_ATTENTION_MAX = 3


def _review_has_images(review: Dict[str, Any]) -> bool:
    for key in ("image_urls", "images", "review_images", "media"):
        value = review.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def seller_attention_query(base_query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    query = dict(base_query or {})
    query["rating"] = {"$lte": LOW_RATING_ATTENTION_MAX}
    query["$or"] = [
        {"trust_analysis.flags.0": {"$exists": True}},
        {"image_evidence.image_relevance_score": {"$lt": 55}},
        {"trust_analysis.review_trust_score": {"$lt": 55}},
    ]
    return query


def _fallback_product_url(review: Dict[str, Any]) -> str:
    external_product_id = str(review.get("external_product_id") or "").strip()
    if not external_product_id:
        return ""

    platform_code = str(review.get("platform_code") or review.get("source") or "").lower()
    if platform_code == "lazada":
        return f"https://www.lazada.vn/products/i{external_product_id}.html"
    if platform_code == "tiki":
        spid = str(review.get("spid") or "").strip()
        suffix = f"?spid={spid}" if spid else ""
        return f"https://tiki.vn/product-p{external_product_id}.html{suffix}"
    if platform_code in {"tiktok_shop", "tiktok"}:
        return f"https://shop.tiktok.com/vn/pdp/{external_product_id}"
    return ""


def _level_vi(level: str) -> str:
    return {
        "strong": "Mạnh",
        "good": "Tốt",
        "medium": "Trung bình",
        "weak": "Yếu",
        "very_weak": "Rất yếu",
    }.get(level, "Chưa rõ")


def _image_fit_answer(review: Dict[str, Any], trust: Dict[str, Any]) -> Dict[str, Any]:
    evidence = review.get("image_evidence") or {}
    has_images = _review_has_images(review) or trust.get("has_images", False)
    score = float(evidence.get("image_relevance_score", trust.get("image_evidence_score", 55 if has_images else 50)))
    status = evidence.get("image_evidence_status") or trust.get("image_evidence_status", "image_present_not_verified" if has_images else "no_review_image")
    if has_images and status == "no_review_image":
        status = "image_present_not_verified"
        score = 55.0

    if not has_images:
        answer = "Không có ảnh để kiểm tra"
        label = "NO_IMAGE"
    elif status == "image_present_not_verified":
        answer = "Có ảnh nhưng chưa chạy phân tích ảnh"
        label = "POSSIBLE_MATCH"
    elif score >= 75:
        answer = "Ảnh có khả năng phù hợp với sản phẩm"
        label = "MATCH"
    elif score >= 55:
        answer = "Ảnh có vẻ liên quan nhưng chưa đủ mạnh"
        label = "POSSIBLE_MATCH"
    elif score >= 35:
        answer = "Ảnh chưa đủ rõ để kết luận"
        label = "UNCLEAR"
    else:
        answer = "Ảnh có dấu hiệu không phù hợp với sản phẩm"
        label = "MISMATCH_RISK"

    return {"label": label, "answer": answer, "score": round(score, 2), "status": status}


def _evidence_answer(trust: Dict[str, Any]) -> Dict[str, Any]:
    trust_score = float(trust.get("review_trust_score", 0))
    specificity = float(trust.get("content_specificity_score", 0))
    image_score = float(trust.get("image_evidence_score", 50))
    has_text = bool(trust.get("has_text", False))
    has_images = bool(trust.get("has_images", False))

    if trust.get("use_as_strong_evidence"):
        label = "STRONG"
        answer = "Review có đủ bằng chứng mạnh để dùng làm insight"
    elif not has_text and not has_images:
        label = "RATING_ONLY"
        answer = "Review chỉ có sao, chỉ nên dùng cho thống kê rating"
    elif specificity < 25 and image_score < 55:
        label = "WEAK"
        answer = "Bằng chứng yếu, không nên dùng làm căn cứ chính"
    elif trust_score >= 55:
        label = "ENOUGH_TO_REFERENCE"
        answer = "Có thể tham khảo, nhưng chưa phải bằng chứng mạnh"
    else:
        label = "WEAK"
        answer = "Bằng chứng chưa đủ rõ"

    return {
        "label": label,
        "answer": answer,
        "content_specificity_score": round(specificity, 2),
        "image_evidence_score": round(image_score, 2),
    }


def _trust_answer(trust: Dict[str, Any]) -> Dict[str, Any]:
    score = float(trust.get("review_trust_score", 0))
    level = str(trust.get("trust_level", "medium"))
    return {
        "label": level.upper(),
        "answer": f"Độ tin cậy {_level_vi(level).lower()}",
        "score": round(score, 2),
        "level": _level_vi(level),
    }


def _action_answer(review: Dict[str, Any], trust: Dict[str, Any]) -> Dict[str, Any]:
    rating = float(review.get("rating", 0) or 0)
    flags = set(trust.get("flags", []))
    image_score = float(trust.get("image_evidence_score", 50))
    trust_score = float(trust.get("review_trust_score", 0))
    negative_aspects = trust.get("negative_aspects", [])

    if rating <= 3 and ("image_may_not_match_product" in flags or (trust.get("has_images") and image_score < 35)):
        return {
            "label": "CHECK_IMAGE_OR_REPORT",
            "answer": "Review 3 sao trở xuống có ảnh đáng nghi; seller nên kiểm tra ảnh và cân nhắc khiếu nại nếu ảnh sai sự thật",
            "priority": "Cao" if rating <= 2 else "Trung bình",
        }
    if rating <= 3 and trust_score >= 65 and negative_aspects:
        return {
            "label": "FIX_PRODUCT_OR_OPERATION",
            "answer": "Review tiêu cực có bằng chứng tương đối rõ; seller nên xử lý vấn đề được nhắc đến",
            "priority": "Cao",
        }
    if "high_rating_with_complaint" in flags:
        return {
            "label": "MONITOR_COMPLAINT",
            "answer": "Review sao cao nhưng vẫn có phàn nàn; seller nên theo dõi để cải thiện vận hành/sản phẩm",
            "priority": "Trung bình",
        }
    if "rating_only_review" in flags:
        return {
            "label": "NO_ACTION",
            "answer": "Chỉ có rating, chưa đủ căn cứ để hành động cụ thể",
            "priority": "Thấp",
        }
    if rating <= 3 and trust_score < 55:
        return {
            "label": "CHECK_REVIEW",
            "answer": "Review 3 sao trở xuống có độ tin cậy thấp, seller nên kiểm tra thêm trước khi dùng làm căn cứ",
            "priority": "Trung bình",
        }
    if rating >= 4 and ("image_may_not_match_product" in flags or image_score < 35):
        return {
            "label": "LOW_PRIORITY_IMAGE_NOTE",
            "answer": "Review sao cao có ảnh chưa khớp, chỉ nên ghi nhận nhẹ và không ưu tiên khiếu nại",
            "priority": "Thấp",
        }
    return {
        "label": "USE_FOR_INSIGHT",
        "answer": "Có thể dùng review này để tổng hợp insight cho seller",
        "priority": "Thấp",
    }


class SellerFeedbackService:
    def __init__(self, db: Database):
        self.db = db

    def product_url_for_review(self, review: Dict[str, Any]) -> str:
        if review.get("product_url"):
            return str(review["product_url"])

        product_id = review.get("product_id")
        if product_id is not None:
            product = self.db.products.find_one({"id": product_id}, {"_id": 0, "product_url": 1})
            if product and product.get("product_url"):
                return str(product["product_url"])

        return _fallback_product_url(review)

    def build_review_decision(self, review: Dict[str, Any]) -> Dict[str, Any]:
        trust = dict(review.get("trust_analysis") or analyze_review_trust(review))
        if _review_has_images(review) and not trust.get("has_images"):
            trust["has_images"] = True
            if trust.get("image_evidence_status") == "no_review_image":
                trust["image_evidence_status"] = "image_present_not_verified"
                trust["image_evidence_score"] = 55.0
        product_url = self.product_url_for_review(review)
        return {
            "review_id": review.get("id"),
            "external_review_id": review.get("external_review_id", ""),
            "product_id": review.get("product_id"),
            "external_product_id": review.get("external_product_id", ""),
            "platform_code": review.get("platform_code", ""),
            "source": review.get("source", ""),
            "product_title": review.get("product_title", ""),
            "product_url": product_url,
            "review_source_url": product_url,
            "rating": review.get("rating"),
            "created_at": review.get("created_at"),
            "review_text": review.get("review_text", ""),
            "image_urls": review.get("image_urls", []),
            "flags": trust.get("flags", []),
            "negative_aspects": trust.get("negative_aspects", []),
            "positive_aspects": trust.get("positive_aspects", []),
            "image_fit": _image_fit_answer(review, trust),
            "evidence": _evidence_answer(trust),
            "trust": _trust_answer(trust),
            "seller_action": _action_answer(review, trust),
        }

    def list_review_decisions(
        self,
        product_id: Optional[int] = None,
        platform_code: Optional[str] = None,
        external_product_id: Optional[str] = None,
        rating: Optional[int] = None,
        only_attention: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if product_id is not None:
            query["product_id"] = product_id
        if platform_code:
            query["platform_code"] = platform_code
        if external_product_id:
            query["external_product_id"] = external_product_id
        if only_attention:
            query = seller_attention_query(query)
        if rating is not None:
            query["rating"] = float(rating)

        cursor = self.db.reviews.find(query, {"_id": 0}).sort([
            ("created_at", -1),
            ("trust_analysis.review_trust_score", 1),
            ("id", -1),
        ]).limit(limit)
        return [self.build_review_decision(review) for review in cursor]

    def list_image_comparisons(
        self,
        product_id: Optional[int] = None,
        platform_code: Optional[str] = None,
        external_product_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"image_urls.0": {"$exists": True}}
        if product_id is not None:
            query["product_id"] = product_id
        if platform_code:
            query["platform_code"] = platform_code
        if external_product_id:
            query["external_product_id"] = external_product_id

        projection = {
            "_id": 0,
            "id": 1,
            "external_review_id": 1,
            "product_id": 1,
            "external_product_id": 1,
            "platform_code": 1,
            "source": 1,
            "product_title": 1,
            "product_url": 1,
            "spid": 1,
            "rating": 1,
            "created_at": 1,
            "review_text": 1,
            "image_urls": 1,
            "image_evidence": 1,
            "trust_analysis": 1,
        }
        analyzed_query = {**query, "image_evidence": {"$exists": True}}
        analyzed = list(self.db.reviews.find(analyzed_query, projection).sort([
            ("created_at", -1),
            ("image_evidence.image_relevance_score", 1),
            ("id", -1),
        ]).limit(limit))
        if len(analyzed) >= limit:
            return [self.build_image_comparison(review) for review in analyzed]

        not_analyzed_query = {**query, "image_evidence": {"$exists": False}}
        remaining = limit - len(analyzed)
        not_analyzed = list(self.db.reviews.find(not_analyzed_query, projection).sort([
            ("created_at", -1),
            ("id", -1),
        ]).limit(remaining))
        return [self.build_image_comparison(review) for review in [*analyzed, *not_analyzed]]

    def build_image_comparison(self, review: Dict[str, Any]) -> Dict[str, Any]:
        evidence = review.get("image_evidence") or {}
        details = evidence.get("details") or []
        first_detail = next((item for item in details if item.get("status") == "ok"), details[0] if details else {})
        trust = review.get("trust_analysis") or analyze_review_trust(review)
        product_url = self.product_url_for_review(review)

        return {
            "review_id": review.get("id"),
            "external_review_id": review.get("external_review_id", ""),
            "product_id": review.get("product_id"),
            "external_product_id": review.get("external_product_id", ""),
            "platform_code": review.get("platform_code", ""),
            "source": review.get("source", ""),
            "product_title": review.get("product_title", ""),
            "product_url": product_url,
            "review_source_url": product_url,
            "rating": review.get("rating"),
            "created_at": review.get("created_at"),
            "review_text": review.get("review_text", ""),
            "image_urls": review.get("image_urls", []),
            "analysis_status": "analyzed" if evidence else "not_analyzed",
            "image_relevance_score": round(float(evidence.get("image_relevance_score", 0)), 2) if evidence else None,
            "image_evidence_status": evidence.get("image_evidence_status", "not_analyzed"),
            "expected_product_labels": evidence.get("expected_product_labels", []),
            "best_expected_label": evidence.get("best_expected_label"),
            "best_other_label": evidence.get("best_other_label"),
            "category_status": evidence.get("category_status"),
            "category_margin": evidence.get("category_margin"),
            "review_claim_type": evidence.get("review_claim_type"),
            "expected_evidence_labels": evidence.get("expected_evidence_labels", []),
            "claim_evidence_score": evidence.get("claim_evidence_score"),
            "claim_evidence_status": evidence.get("claim_evidence_status"),
            "best_claim_label": evidence.get("best_claim_label"),
            "best_other_evidence_label": evidence.get("best_other_evidence_label"),
            "images_analyzed": evidence.get("images_analyzed", 0),
            "product_images_used": evidence.get("product_images_used", 0),
            "text_score": first_detail.get("text_score"),
            "product_image_score": first_detail.get("product_image_score"),
            "category_score": first_detail.get("category_score"),
            "image_hash": first_detail.get("image_hash"),
            "flags": trust.get("flags", []),
            "trust": _trust_answer(trust),
        }

    def product_feedback_summary(
        self,
        product_id: Optional[int] = None,
        platform_code: Optional[str] = None,
        external_product_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if product_id is not None:
            query["product_id"] = product_id
        if platform_code:
            query["platform_code"] = platform_code
        if external_product_id:
            query["external_product_id"] = external_product_id

        total = self.db.reviews.count_documents(query)
        with_images = self.db.reviews.count_documents({**query, "image_urls.0": {"$exists": True}})
        with_image_analysis = self.db.reviews.count_documents({**query, "image_evidence": {"$exists": True}})
        with_text = self.db.reviews.count_documents({**query, "review_text": {"$ne": ""}})

        trust_levels: Counter[str] = Counter()
        flagged = 0
        trust_sum = 0.0
        trust_count = 0

        for review in self.db.reviews.find(query, {"_id": 0}):
            decision = self.build_review_decision(review)
            trust_levels[decision["trust"]["level"]] += 1
            if float(review.get("rating", 0) or 0) <= LOW_RATING_ATTENTION_MAX and decision["flags"]:
                flagged += 1
            trust_sum += float(decision["trust"]["score"])
            trust_count += 1

        attention = self.list_review_decisions(
            product_id=product_id,
            platform_code=platform_code,
            external_product_id=external_product_id,
            only_attention=True,
            limit=10,
        )

        return {
            "total_reviews": total,
            "reviews_with_text": with_text,
            "reviews_with_images": with_images,
            "reviews_with_image_analysis": with_image_analysis,
            "average_trust_score": round(trust_sum / trust_count, 2) if trust_count else 0,
            "flagged_reviews": flagged,
            "trust_level_counts": dict(trust_levels),
            "attention_reviews": attention,
        }
