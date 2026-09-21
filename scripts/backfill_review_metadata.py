import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.db.database import db, ensure_indexes, utcnow
from app.ml.image_evidence import extract_image_urls


def main() -> None:
    ensure_indexes(db)
    now = utcnow()
    products = {product["id"]: product for product in db.products.find({}, {"_id": 0})}
    platforms = {platform["id"]: platform for platform in db.platforms.find({}, {"_id": 0})}

    total = 0
    updated = 0
    for review in db.reviews.find({}):
        product = products.get(review.get("product_id"))
        if not product:
            continue
        platform = platforms.get(product.get("platform_id"), {})
        image_urls = extract_image_urls(review.get("images") or review.get("review_images") or review.get("image_urls"))
        update = {
            "platform_id": product.get("platform_id"),
            "platform_code": platform.get("code", ""),
            "source": (review.get("source") or platform.get("code", "")).upper(),
            "external_product_id": product.get("external_product_id", ""),
            "product_title": product.get("title", ""),
            "metadata_backfilled_at": now,
        }
        if image_urls:
            update["image_urls"] = image_urls

        db.reviews.update_one({"_id": review["_id"]}, {"$set": update})
        trust = db.review_trust_analyses.find_one({"review_id": review.get("id")})
        if trust:
            db.review_trust_analyses.update_one(
                {"review_id": review["id"]},
                {
                    "$set": {
                        "platform_code": update["platform_code"],
                        "source": update["source"],
                        "external_product_id": update["external_product_id"],
                        "product_title": update["product_title"],
                        "updated_at": now,
                    }
                },
            )
        total += 1
        updated += 1

    print("Hoan tat bo sung nhan san/pham cho review.")
    print(f"Tong review quet: {total}")
    print(f"Review da cap nhat: {updated}")
    print("Bay gio co the loc trong Mongo Compass bang:")
    print('{ "platform_code": "tiki", "external_product_id": "86517373" }')
    print('{ "platform_code": "lazada", "external_product_id": "310626559" }')


if __name__ == "__main__":
    main()
