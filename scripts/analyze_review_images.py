import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.db.database import db, ensure_indexes, utcnow
from app.ml.image_evidence import analyze_review_image_relevance
from app.ml.review_trust import analyze_review_trust


def main() -> None:
    parser = argparse.ArgumentParser(description="Use OpenCLIP to score whether review images match the product.")
    parser.add_argument("--product-id", type=int, default=None, help="Internal Mongo product id. Omit to scan all products.")
    parser.add_argument("--product-text", default="", help="Manual product description/title for better image matching.")
    parser.add_argument("--limit", type=int, default=20, help="How many image reviews to analyze. Use 0 for all.")
    parser.add_argument("--max-images-per-review", type=int, default=2)
    args = parser.parse_args()

    ensure_indexes(db)

    query = {
        "$or": [
            {"images.0": {"$exists": True}},
            {"review_images.0": {"$exists": True}},
            {"image_urls.0": {"$exists": True}},
        ]
    }
    if args.product_id is not None:
        query["product_id"] = args.product_id

    cursor = db.reviews.find(query).sort("created_at", -1)
    if args.limit > 0:
        cursor = cursor.limit(args.limit)

    total = 0
    failed = 0
    now = utcnow()

    for review in cursor:
        product = db.products.find_one({"id": review["product_id"]}, {"_id": 0})
        result = analyze_review_image_relevance(
            review,
            product=product,
            product_text=args.product_text,
            max_images=args.max_images_per_review,
        )
        if result["images_analyzed"] == 0:
            failed += 1

        db.reviews.update_one(
            {"_id": review["_id"]},
            {
                "$set": {
                    "image_evidence": result,
                    "image_relevance_score": result["image_relevance_score"],
                    "image_analyzed_at": now,
                }
            },
        )

        updated_review = dict(review)
        updated_review["image_relevance_score"] = result["image_relevance_score"]
        updated_review["image_evidence_status"] = result["image_evidence_status"]
        updated_review["claim_evidence_status"] = result.get("claim_evidence_status")
        updated_review["claim_evidence_score"] = result.get("claim_evidence_score")
        trust = analyze_review_trust(updated_review)
        db.reviews.update_one(
            {"_id": review["_id"]},
            {"$set": {"trust_analysis": trust, "trust_analyzed_at": now}},
        )
        db.review_trust_analyses.update_one(
            {"review_id": review["id"]},
            {"$set": {"review_id": review["id"], "product_id": review["product_id"], "analysis": trust, "updated_at": now}},
            upsert=True,
        )

        total += 1
        print(
            f"review {review['id']}: image_score={result['image_relevance_score']} "
            f"status={result['image_evidence_status']} trust={trust['review_trust_score']}"
        )

    print("Hoan tat phan tich anh review.")
    print(f"Tong review anh da xu ly: {total}")
    print(f"So review anh chua doc duoc: {failed}")
    print("Ket qua luu vao reviews.image_evidence va reviews.trust_analysis")


if __name__ == "__main__":
    main()
