import datetime

from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.product_repo import ProductRepository
from app.db.repositories.review_repo import ReviewRepository
from app.services.seller_feedback import SellerFeedbackService


def test_seller_feedback_answers_four_core_questions(db_session):
    platform = PlatformRepository(db_session).get_or_create("tiki", "Tiki")
    ProductRepository(db_session).bulk_upsert_products([
        {
            "platform_id": platform.id,
            "external_product_id": "P_FEEDBACK",
            "title": "Ao thun cotton",
            "normalized_title": "ao thun cotton",
            "product_url": "https://tiki.vn/product-pP_FEEDBACK.html",
        }
    ])
    product = ProductRepository(db_session).get_by_external_id(platform.id, "P_FEEDBACK")
    ReviewRepository(db_session).bulk_upsert_reviews([
        {
            "product_id": product.id,
            "platform_id": platform.id,
            "platform_code": "tiki",
            "source": "TIKI",
            "external_product_id": "P_FEEDBACK",
            "product_title": "Ao thun cotton",
            "external_review_id": "R_BAD_IMAGE",
            "rating": 1,
            "review_text": "Ao bi rach duong may",
            "image_urls": ["https://example.com/not-product.jpg"],
            "image_relevance_score": 20,
            "image_evidence_status": "image_may_not_match_product",
        }
    ])

    decision = SellerFeedbackService(db_session).list_review_decisions(product_id=product.id)[0]

    assert decision["image_fit"]["label"] == "MISMATCH_RISK"
    assert decision["evidence"]["label"] in {"WEAK", "ENOUGH_TO_REFERENCE"}
    assert decision["trust"]["score"] < 70
    assert decision["seller_action"]["label"] == "CHECK_IMAGE_OR_REPORT"
    assert decision["product_url"] == "https://tiki.vn/product-pP_FEEDBACK.html"
    assert decision["review_source_url"] == "https://tiki.vn/product-pP_FEEDBACK.html"


def test_high_rating_bad_image_is_not_seller_attention(db_session):
    platform = PlatformRepository(db_session).get_or_create("lazada", "Lazada")
    ProductRepository(db_session).bulk_upsert_products([
        {"platform_id": platform.id, "external_product_id": "P_HIGH", "title": "Serum", "normalized_title": "serum"}
    ])
    product = ProductRepository(db_session).get_by_external_id(platform.id, "P_HIGH")
    ReviewRepository(db_session).bulk_upsert_reviews([
        {
            "product_id": product.id,
            "platform_id": platform.id,
            "platform_code": "lazada",
            "source": "LAZADA",
            "external_product_id": "P_HIGH",
            "product_title": "Serum",
            "external_review_id": "R_HIGH_BAD_IMAGE",
            "rating": 5,
            "review_text": "San pham ok",
            "image_urls": ["https://example.com/not-product.jpg"],
            "trust_analysis": {
                "has_images": True,
                "image_evidence_score": 20,
                "review_trust_score": 45,
                "trust_level": "medium",
                "flags": ["image_may_not_match_product"],
            },
        }
    ])

    service = SellerFeedbackService(db_session)
    attention = service.list_review_decisions(product_id=product.id, only_attention=True)
    decision = service.build_review_decision(db_session.reviews.find_one({"external_review_id": "R_HIGH_BAD_IMAGE"}))

    assert attention == []
    assert decision["seller_action"]["label"] == "LOW_PRIORITY_IMAGE_NOTE"


def test_seller_attention_prioritizes_recent_comments(db_session):
    platform = PlatformRepository(db_session).get_or_create("lazada", "Lazada")
    ProductRepository(db_session).bulk_upsert_products([
        {"platform_id": platform.id, "external_product_id": "P_RECENT", "title": "Serum", "normalized_title": "serum"}
    ])
    product = ProductRepository(db_session).get_by_external_id(platform.id, "P_RECENT")
    ReviewRepository(db_session).bulk_upsert_reviews([
        {
            "product_id": product.id,
            "platform_id": platform.id,
            "platform_code": "lazada",
            "source": "LAZADA",
            "external_product_id": "P_RECENT",
            "product_title": "Serum",
            "external_review_id": "OLD_BAD",
            "rating": 1,
            "review_text": "Te",
            "created_at": datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
            "trust_analysis": {"review_trust_score": 10, "trust_level": "very_weak", "flags": ["low_rating_without_clear_reason"]},
        },
        {
            "product_id": product.id,
            "platform_id": platform.id,
            "platform_code": "lazada",
            "source": "LAZADA",
            "external_product_id": "P_RECENT",
            "product_title": "Serum",
            "external_review_id": "NEW_BAD",
            "rating": 2,
            "review_text": "Khong on",
            "created_at": datetime.datetime(2026, 2, 1, tzinfo=datetime.timezone.utc),
            "trust_analysis": {"review_trust_score": 45, "trust_level": "medium", "flags": ["low_rating_without_clear_reason"]},
        },
    ])

    attention = SellerFeedbackService(db_session).list_review_decisions(product_id=product.id, only_attention=True)

    assert [item["external_review_id"] for item in attention] == ["NEW_BAD", "OLD_BAD"]


def test_seller_feedback_api_summary(client_app, db_session):
    platform = PlatformRepository(db_session).get_or_create("tiki", "Tiki")
    ProductRepository(db_session).bulk_upsert_products([
        {"platform_id": platform.id, "external_product_id": "P_API", "title": "Book", "normalized_title": "book"}
    ])
    product = ProductRepository(db_session).get_by_external_id(platform.id, "P_API")
    ReviewRepository(db_session).bulk_upsert_reviews([
        {
            "product_id": product.id,
            "platform_id": platform.id,
            "platform_code": "tiki",
            "source": "TIKI",
            "external_product_id": "P_API",
            "product_title": "Book",
            "external_review_id": "R_API",
            "rating": 5,
            "review_text": "Sach dep nhung dong goi bi mop",
        }
    ])

    res = client_app.get(f"/api/v1/seller-feedback/summary?product_id={product.id}")
    assert res.status_code == 200
    body = res.json()
    assert body["total_reviews"] == 1
    assert "attention_reviews" in body


def test_seller_feedback_image_comparison_api(client_app, db_session):
    platform = PlatformRepository(db_session).get_or_create("tiki", "Tiki")
    ProductRepository(db_session).bulk_upsert_products([
        {
            "platform_id": platform.id,
            "external_product_id": "P_IMG",
            "title": "Book",
            "normalized_title": "book",
            "product_url": "https://tiki.vn/product-pP_IMG.html",
        }
    ])
    product = ProductRepository(db_session).get_by_external_id(platform.id, "P_IMG")
    ReviewRepository(db_session).bulk_upsert_reviews([
        {
            "product_id": product.id,
            "platform_id": platform.id,
            "platform_code": "tiki",
            "source": "TIKI",
            "external_product_id": "P_IMG",
            "product_title": "Book",
            "external_review_id": "R_IMG",
            "rating": 5,
            "review_text": "Sach dep",
            "image_urls": ["https://example.com/review.jpg"],
            "image_evidence": {
                "image_relevance_score": 82,
                "image_evidence_status": "image_likely_matches_product",
                "expected_product_labels": ["a book"],
                "best_expected_label": "a book",
                "best_other_label": "a food item",
                "details": [{"status": "ok", "text_score": 90, "product_image_score": 70, "category_score": 88}],
            },
        }
    ])

    res = client_app.get("/api/v1/seller-feedback/image-comparisons?platform_code=tiki&external_product_id=P_IMG")
    assert res.status_code == 200
    body = res.json()
    assert body[0]["analysis_status"] == "analyzed"
    assert body[0]["image_relevance_score"] == 82
    assert body[0]["text_score"] == 90
    assert body[0]["product_url"] == "https://tiki.vn/product-pP_IMG.html"


def test_resolve_lazada_product_link_prefers_path_item_id(client_app):
    url = (
        "https://www.lazada.vn/products/sua-rua-mat-i2103900853-s9888870612.html"
        "?pdp_item=310626559&itemId=2103900853"
    )

    res = client_app.post("/api/v1/seller-feedback/resolve-product-link", json={"product_url": url})

    assert res.status_code == 200
    body = res.json()
    assert body["platform_code"] == "lazada"
    assert body["external_product_id"] == "2103900853"
    assert body["detected_from"] == "path_item_id"
    assert body["candidate_product_ids"]["tracking_pdp_item"] == "310626559"


def test_resolve_tiki_product_link(client_app):
    url = "https://tiki.vn/sach-test-p86517373.html?spid=86517374"

    res = client_app.post("/api/v1/seller-feedback/resolve-product-link", json={"product_url": url})

    assert res.status_code == 200
    body = res.json()
    assert body["platform_code"] == "tiki"
    assert body["external_product_id"] == "86517373"
    assert body["spid"] == "86517374"


def test_resolve_tiktok_shop_product_link(client_app):
    url = "https://shop.tiktok.com/vn/pdp/op-dien-thoai/1730279169693551229?source=ecommerce_mall"

    res = client_app.post("/api/v1/seller-feedback/resolve-product-link", json={"product_url": url})

    assert res.status_code == 200
    body = res.json()
    assert body["platform_code"] == "tiktok_shop"
    assert body["external_product_id"] == "1730279169693551229"
    assert body["detected_from"] == "path_product_id"


def test_seller_feedback_does_not_hide_images_when_trust_analysis_is_stale(db_session):
    service = SellerFeedbackService(db_session)
    decision = service.build_review_decision(
        {
            "id": 1,
            "external_review_id": "STALE_IMAGE",
            "rating": 1,
            "review_text": "Hang ok ah.",
            "image_urls": ["https://example.com/review.jpg"],
            "trust_analysis": {
                "has_images": False,
                "image_evidence_score": 50,
                "image_evidence_status": "no_review_image",
                "review_trust_score": 39.7,
                "trust_level": "weak",
                "flags": ["rating_text_mismatch"],
            },
        }
    )

    assert decision["image_fit"]["label"] == "POSSIBLE_MATCH"
    assert decision["image_fit"]["score"] == 55.0
    assert decision["image_fit"]["answer"] == "Có ảnh nhưng chưa chạy phân tích ảnh"
