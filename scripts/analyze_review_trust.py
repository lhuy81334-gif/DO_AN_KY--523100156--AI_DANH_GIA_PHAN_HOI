import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.db.database import db, ensure_indexes, utcnow
from app.ml.review_trust import analyze_review_trust


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze review trust and evidence quality in MongoDB")
    parser.add_argument("--product-id", type=int, default=None, help="Internal Mongo product id. Omit to analyze all reviews.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of reviews. 0 means all.")
    args = parser.parse_args()

    ensure_indexes(db)
    query = {}
    if args.product_id is not None:
        query["product_id"] = args.product_id

    cursor = db.reviews.find(query).sort("created_at", -1)
    if args.limit > 0:
        cursor = cursor.limit(args.limit)

    total = 0
    levels = {}
    flagged = 0
    now = utcnow()

    for review in cursor:
        analysis = analyze_review_trust(review)
        total += 1
        levels[analysis["trust_level"]] = levels.get(analysis["trust_level"], 0) + 1
        if analysis["flags"]:
            flagged += 1

        db.reviews.update_one(
            {"_id": review["_id"]},
            {"$set": {"trust_analysis": analysis, "trust_analyzed_at": now}},
        )
        db.review_trust_analyses.update_one(
            {"review_id": review["id"]},
            {
                "$set": {
                    "review_id": review["id"],
                    "product_id": review["product_id"],
                    "analysis": analysis,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    print("Hoan tat phan tich do tin cay review.")
    print(f"Tong review da xu ly: {total}")
    print(f"So review co canh bao: {flagged}")
    print(f"Phan bo trust level: {levels}")
    print("Ket qua da luu vao:")
    print("- collection reviews, field trust_analysis")
    print("- collection review_trust_analyses")


if __name__ == "__main__":
    main()
