from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.product_repo import ProductRepository
from app.ingestion.json_importer import JSONImporter


def test_imported_review_keeps_platform_and_product_metadata(db_session, tmp_path):
    platform = PlatformRepository(db_session).get_or_create("tiki", "Tiki")
    ProductRepository(db_session).bulk_upsert_products([
        {
            "platform_id": platform.id,
            "external_product_id": "P_123",
            "title": "Test Product",
            "normalized_title": "test product",
        }
    ])
    path = tmp_path / "reviews.json"
    path.write_text(
        """
        [
          {
            "external_product_id": "P_123",
            "external_review_id": "R_123",
            "rating": 5,
            "review_text": "San pham tot",
            "images": [{"full_path": "https://example.com/review.jpg"}]
          }
        ]
        """,
        encoding="utf-8",
    )

    stats = JSONImporter(db_session).import_reviews_file(str(path), platform_code="tiki")
    saved = db_session.reviews.find_one({"external_review_id": "R_123"}, {"_id": 0})

    assert stats["inserted"] == 1
    assert saved["platform_code"] == "tiki"
    assert saved["source"] == "TIKI"
    assert saved["external_product_id"] == "P_123"
    assert saved["product_title"] == "Test Product"
    assert saved["images"][0]["full_path"] == "https://example.com/review.jpg"


def test_imported_review_uses_source_comment_time(db_session, tmp_path):
    platform = PlatformRepository(db_session).get_or_create("tiki", "Tiki")
    ProductRepository(db_session).bulk_upsert_products([
        {
            "platform_id": platform.id,
            "external_product_id": "P_TIME",
            "title": "Time Product",
            "normalized_title": "time product",
        }
    ])
    path = tmp_path / "reviews_time.json"
    path.write_text(
        """
        [
          {
            "external_product_id": "P_TIME",
            "external_review_id": "R_TIME",
            "rating": 4,
            "review_text": "San pham dung nhu mo ta",
            "raw_created_at": 1623043545
          }
        ]
        """,
        encoding="utf-8",
    )

    stats = JSONImporter(db_session).import_reviews_file(str(path), platform_code="tiki")
    saved = db_session.reviews.find_one({"external_review_id": "R_TIME"}, {"_id": 0})

    assert stats["inserted"] == 1
    assert saved["created_at"].year == 2021
    assert saved["collected_at"].year >= 2026
    assert saved["raw_created_at"] == 1623043545
