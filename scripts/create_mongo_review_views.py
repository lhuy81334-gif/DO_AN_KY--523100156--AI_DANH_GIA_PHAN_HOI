import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.db.database import db


VIEWS = {
    "reviews_tiki": [
        {"$match": {"platform_code": "tiki"}},
        {"$sort": {"created_at": -1}},
    ],
    "reviews_lazada": [
        {"$match": {"platform_code": "lazada"}},
        {"$sort": {"created_at": -1}},
    ],
    "reviews_tiktok_shop": [
        {"$match": {"platform_code": "tiktok_shop"}},
        {"$sort": {"created_at": -1}},
    ],
    "reviews_with_images": [
        {"$match": {"image_urls.0": {"$exists": True}}},
        {"$sort": {"created_at": -1}},
    ],
    "reviews_tiki_with_images": [
        {"$match": {"platform_code": "tiki", "image_urls.0": {"$exists": True}}},
        {"$sort": {"created_at": -1}},
    ],
    "reviews_lazada_with_images": [
        {"$match": {"platform_code": "lazada", "image_urls.0": {"$exists": True}}},
        {"$sort": {"created_at": -1}},
    ],
    "reviews_tiktok_shop_with_images": [
        {"$match": {"platform_code": "tiktok_shop", "image_urls.0": {"$exists": True}}},
        {"$sort": {"created_at": -1}},
    ],
    "reviews_need_seller_attention": [
        {
            "$match": {
                "$or": [
                    {"trust_analysis.flags.0": {"$exists": True}},
                    {"image_evidence.image_relevance_score": {"$lt": 55}},
                    {"trust_analysis.review_trust_score": {"$lt": 55}},
                ]
            }
        },
        {"$sort": {"trust_analysis.review_trust_score": 1}},
    ],
    "reviews_tiki_need_seller_attention": [
        {
            "$match": {
                "platform_code": "tiki",
                "$or": [
                    {"trust_analysis.flags.0": {"$exists": True}},
                    {"image_evidence.image_relevance_score": {"$lt": 55}},
                    {"trust_analysis.review_trust_score": {"$lt": 55}},
                ],
            }
        },
        {"$sort": {"trust_analysis.review_trust_score": 1}},
    ],
    "reviews_lazada_need_seller_attention": [
        {
            "$match": {
                "platform_code": "lazada",
                "$or": [
                    {"trust_analysis.flags.0": {"$exists": True}},
                    {"image_evidence.image_relevance_score": {"$lt": 55}},
                    {"trust_analysis.review_trust_score": {"$lt": 55}},
                ],
            }
        },
        {"$sort": {"trust_analysis.review_trust_score": 1}},
    ],
    "reviews_tiktok_shop_need_seller_attention": [
        {
            "$match": {
                "platform_code": "tiktok_shop",
                "$or": [
                    {"trust_analysis.flags.0": {"$exists": True}},
                    {"image_evidence.image_relevance_score": {"$lt": 55}},
                    {"trust_analysis.review_trust_score": {"$lt": 55}},
                ],
            }
        },
        {"$sort": {"trust_analysis.review_trust_score": 1}},
    ],
}


def collection_type(name: str) -> str | None:
    rows = list(db.list_collections(filter={"name": name}))
    if not rows:
        return None
    return rows[0].get("type")


def create_or_replace_view(name: str, pipeline: list[dict]) -> str:
    existing_type = collection_type(name)
    if existing_type == "collection":
        return f"Bo qua {name}: da ton tai collection that, khong ghi de."
    if existing_type == "view":
        db.drop_collection(name)
    db.create_collection(name, viewOn="reviews", pipeline=pipeline)
    return f"Da tao view {name} -> reviews"


def main() -> None:
    print(f"Database: {db.name}")
    for name, pipeline in VIEWS.items():
        print(create_or_replace_view(name, pipeline))
    print("\nTrong Mongo Compass, bam Refresh roi xem cac view:")
    for name in VIEWS:
        print(f"- {name}")


if __name__ == "__main__":
    main()
