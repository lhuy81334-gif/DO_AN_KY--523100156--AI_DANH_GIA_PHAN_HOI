import os
import sys
import argparse
import json
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.db.database import db, ensure_indexes, utcnow
from app.ingestion.normalizer import DataNormalizer


def backfill_from_mongo_raw() -> tuple[int, int, int]:
    total = updated = skipped = 0
    now = utcnow()
    cursor = db.reviews.find({"raw_created_at": {"$exists": True}}, {"raw_created_at": 1})
    for review in cursor:
        total += 1
        parsed = DataNormalizer.normalize_datetime(review.get("raw_created_at"))
        if not parsed:
            skipped += 1
            continue
        db.reviews.update_one(
            {"_id": review["_id"]},
            {
                "$set": {
                    "created_at": parsed,
                    "created_at_backfilled_at": now,
                }
            },
        )
        updated += 1
    return total, updated, skipped


def backfill_from_file(path: Path, platform_code: str | None = None) -> tuple[int, int, int]:
    total = updated = skipped = 0
    now = utcnow()
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        rows = [rows]

    for row in rows:
        total += 1
        raw_created_at = row.get("raw_created_at") or row.get("created_at")
        parsed = DataNormalizer.normalize_datetime(raw_created_at)
        external_product_id = str(row.get("external_product_id") or row.get("product_id") or "")
        external_review_id = str(row.get("external_review_id") or row.get("review_id") or row.get("id") or "")
        if not parsed or not external_product_id or not external_review_id:
            skipped += 1
            continue

        query = {
            "external_product_id": external_product_id,
            "external_review_id": external_review_id,
        }
        if platform_code:
            query["platform_code"] = platform_code
        elif row.get("platform_code"):
            query["platform_code"] = row["platform_code"]

        result = db.reviews.update_one(
            query,
            {
                "$set": {
                    "created_at": parsed,
                    "raw_created_at": raw_created_at,
                    "created_at_backfilled_at": now,
                }
            },
        )
        if result.matched_count:
            updated += 1
        else:
            skipped += 1

    return total, updated, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Cap nhat reviews.created_at bang thoi gian comment goc tu API.")
    parser.add_argument("--reviews-file", help="File JSON normalized co raw_created_at/created_at goc.")
    parser.add_argument("--platform-code", help="tiki hoac lazada, dung de match chinh xac hon.")
    args = parser.parse_args()

    ensure_indexes(db)
    if args.reviews_file:
        total, updated, skipped = backfill_from_file(Path(args.reviews_file), args.platform_code)
    else:
        total, updated, skipped = backfill_from_mongo_raw()

    print("Hoan tat cap nhat created_at tu raw_created_at.")
    print(f"Review co raw_created_at: {total}")
    print(f"Review da cap nhat: {updated}")
    print(f"Review bo qua vi khong doc duoc thoi gian: {skipped}")


if __name__ == "__main__":
    main()
