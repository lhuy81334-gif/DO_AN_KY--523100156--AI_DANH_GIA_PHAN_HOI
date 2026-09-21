import datetime
import re
from typing import Any, Dict, List, Optional, Tuple

from pymongo import UpdateOne
from pymongo.database import Database

from app.db.database import next_sequence, to_obj, to_objs, utcnow


class ProductRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_by_id(self, product_id: int):
        return to_obj(self.db.products.find_one({"id": product_id}))

    def get_by_external_id(self, platform_id: int, external_product_id: str):
        return to_obj(self.db.products.find_one({"platform_id": platform_id, "external_product_id": str(external_product_id)}))

    def get_total_count(self) -> int:
        return self.db.products.count_documents({})

    def get_paginated(self, page: int = 1, page_size: int = 20, search: Optional[str] = None, category: Optional[str] = None, platform_id: Optional[int] = None) -> Tuple[List, int]:
        query: Dict[str, Any] = {}
        if platform_id:
            query["platform_id"] = platform_id
        if category:
            query["category"] = {"$regex": re.escape(category), "$options": "i"}
        if search:
            clean = search.strip().lower()
            query["$or"] = [
                {"normalized_title": {"$regex": re.escape(clean), "$options": "i"}},
                {"description": {"$regex": re.escape(clean), "$options": "i"}},
            ]
        total = self.db.products.count_documents(query)
        skip = (page - 1) * page_size
        docs = self.db.products.find(query).sort([("sold_count", -1), ("id", -1)]).skip(skip).limit(page_size)
        return to_objs(docs), total

    def bulk_upsert_products(self, batch_data: List[Dict[str, Any]]) -> Dict[str, int]:
        stats = {"inserted": 0, "updated": 0, "duplicated": 0, "failed": 0}
        if not batch_data:
            return stats
        now = utcnow()
        ops = []
        for row in batch_data:
            try:
                row = dict(row)
                row.setdefault("id", next_sequence("products"))
                row.setdefault("shop_id", None)
                row.setdefault("description", "")
                row.setdefault("category", "T-Shirts")
                row.setdefault("price", 0.0)
                row.setdefault("currency", "USD")
                row.setdefault("rating", 0.0)
                row.setdefault("review_count", 0)
                row.setdefault("sold_count", 0)
                row.setdefault("product_url", "")
                row.setdefault("created_at", now)
                row.setdefault("collected_at", now)
                row["updated_at"] = now
                existing = self.db.products.find_one({"platform_id": row["platform_id"], "external_product_id": row["external_product_id"]}, {"id": 1})
                if existing:
                    stats["updated"] += 1
                    row.pop("id", None)
                    row.pop("created_at", None)
                    ops.append(UpdateOne({"platform_id": row["platform_id"], "external_product_id": row["external_product_id"]}, {"$set": row}, upsert=False))
                else:
                    stats["inserted"] += 1
                    ops.append(UpdateOne({"platform_id": row["platform_id"], "external_product_id": row["external_product_id"]}, {"$setOnInsert": row}, upsert=True))
            except Exception:
                stats["failed"] += 1
        if ops:
            self.db.products.bulk_write(ops, ordered=False)
        return stats
