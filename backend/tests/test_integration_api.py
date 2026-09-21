from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.product_repo import ProductRepository
from app.db.repositories.review_repo import ReviewRepository


def test_api_review_feedback_integration(client_app, db_session):
    health = client_app.get("/api/v1/health")
    assert health.status_code == 200

    platform = PlatformRepository(db_session).get_or_create("tiki", "Tiki")
    products = ProductRepository(db_session)
    products.bulk_upsert_products([
        {"platform_id": platform.id, "external_product_id": "INT_P1", "title": "Golden Retriever Mom Graphic T-Shirt", "normalized_title": "golden retriever mom graphic t-shirt", "category": "T-Shirt", "price": 21.99, "rating": 4.8, "sold_count": 1500, "review_count": 180},
        {"platform_id": platform.id, "external_product_id": "INT_P2", "title": "Dog Lover Retro Sweatshirt", "normalized_title": "dog lover retro sweatshirt", "category": "Sweatshirt", "price": 32.99, "rating": 4.5, "sold_count": 800, "review_count": 90},
    ])
    p1 = products.get_by_external_id(platform.id, "INT_P1")
    reviews = ReviewRepository(db_session)
    reviews.bulk_upsert_reviews([
        {
            "product_id": p1.id,
            "platform_id": platform.id,
            "platform_code": "tiki",
            "source": "TIKI",
            "external_product_id": "INT_P1",
            "product_title": "Golden Retriever Mom Graphic T-Shirt",
            "external_review_id": "INT_R1",
            "rating": 5,
            "review_text": "Love this golden retriever shirt, super comfortable!",
        },
        {
            "product_id": p1.id,
            "platform_id": platform.id,
            "platform_code": "tiki",
            "source": "TIKI",
            "external_product_id": "INT_P1",
            "product_title": "Golden Retriever Mom Graphic T-Shirt",
            "external_review_id": "INT_R2",
            "rating": 2,
            "review_text": "Size runs very small and tight.",
        },
    ])
    r1 = db_session.reviews.find_one({"external_review_id": "INT_R1"})
    r2 = db_session.reviews.find_one({"external_review_id": "INT_R2"})
    reviews.add_review_aspects([
        {"review_id": r1["id"], "product_id": p1.id, "aspect": "design", "sentiment": "positive", "confidence": 0.9},
        {"review_id": r2["id"], "product_id": p1.id, "aspect": "size", "sentiment": "negative", "confidence": 0.9},
    ])
    db_session.reviews.update_one(
        {"external_review_id": "INT_R2"},
        {"$set": {"trust_analysis": {"flags": ["low_rating_without_clear_reason"], "review_trust_score": 45}}},
    )

    summary = client_app.get(f"/api/v1/seller-feedback/summary?product_id={p1.id}")
    assert summary.status_code == 200
    assert summary.json()["total_reviews"] == 2

    decisions = client_app.get(f"/api/v1/seller-feedback/reviews?product_id={p1.id}&only_attention=true")
    assert decisions.status_code == 200
    assert len(decisions.json()) >= 1
