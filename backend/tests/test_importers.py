from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.product_repo import ProductRepository
from app.db.repositories.review_repo import ReviewRepository


def test_product_bulk_upsert_and_duplicate_detection(db_session):
    platform = PlatformRepository(db_session).get_or_create("tiki", "Tiki")
    repo = ProductRepository(db_session)
    stats_1 = repo.bulk_upsert_products([
        {"platform_id": platform.id, "external_product_id": "P_001", "title": "Corgi Mom Shirt", "normalized_title": "corgi mom shirt", "category": "T-Shirt", "price": 18.99},
        {"platform_id": platform.id, "external_product_id": "P_002", "title": "Cat Dad Mug", "normalized_title": "cat dad mug", "category": "Mug", "price": 14.99},
    ])
    assert stats_1["inserted"] == 2
    stats_2 = repo.bulk_upsert_products([
        {"platform_id": platform.id, "external_product_id": "P_001", "title": "Corgi Mom Shirt Updated", "normalized_title": "corgi mom shirt updated", "category": "T-Shirt", "price": 21.99}
    ])
    product = repo.get_by_external_id(platform.id, "P_001")
    assert stats_2["updated"] == 1
    assert product.title == "Corgi Mom Shirt Updated"
    assert product.price == 21.99


def test_review_bulk_upsert_and_aspect_aggregation(db_session):
    platform = PlatformRepository(db_session).get_or_create("tiki", "Tiki")
    products = ProductRepository(db_session)
    reviews = ReviewRepository(db_session)
    products.bulk_upsert_products([{"platform_id": platform.id, "external_product_id": "P_REV", "title": "Dog Hoodie", "normalized_title": "dog hoodie"}])
    product = products.get_by_external_id(platform.id, "P_REV")
    stats = reviews.bulk_upsert_reviews([
        {"product_id": product.id, "external_review_id": "R_001", "rating": 5, "review_text": "Great design"},
        {"product_id": product.id, "external_review_id": "R_002", "rating": 2, "review_text": "Size is too small"},
    ])
    saved = db_session.reviews.find_one({"external_review_id": "R_001"})
    saved_2 = db_session.reviews.find_one({"external_review_id": "R_002"})
    reviews.add_review_aspects([
        {"review_id": saved["id"], "product_id": product.id, "aspect": "design", "sentiment": "positive", "confidence": 0.9},
        {"review_id": saved_2["id"], "product_id": product.id, "aspect": "size", "sentiment": "negative", "confidence": 0.9},
    ])
    agg = reviews.get_aspect_sentiment_aggregations([product.id])
    assert stats["inserted"] == 2
    assert agg["design"]["positive"] == 1
    assert agg["size"]["negative"] == 1
