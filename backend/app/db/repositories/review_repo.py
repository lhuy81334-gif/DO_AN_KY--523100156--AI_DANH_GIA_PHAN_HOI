from typing import Any, Dict, List, Optional, Tuple
from pymongo import UpdateOne
from pymongo.database import Database
from app.db.database import next_sequence, to_obj, to_objs, utcnow


class ReviewRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_by_id(self, review_id: int):
        review = self.db.reviews.find_one({"id": review_id})
        if review:
            review["aspects"] = to_objs(self.db.review_aspects.find({"review_id": review_id}))
        return to_obj(review)

    def get_total_count(self) -> int:
        return self.db.reviews.count_documents({})

    def get_paginated_by_product(self, product_id: int, page: int = 1, page_size: int = 20, rating: Optional[float] = None) -> Tuple[List, int]:
        query: Dict[str, Any] = {"product_id": product_id}
        if rating is not None:
            query["rating"] = rating
        total = self.db.reviews.count_documents(query)
        skip = (page - 1) * page_size
        docs = list(self.db.reviews.find(query).sort("created_at", -1).skip(skip).limit(page_size))
        for doc in docs:
            doc["aspects"] = to_objs(self.db.review_aspects.find({"review_id": doc["id"]}))
        return to_objs(docs), total

    def get_aspect_sentiment_aggregations(self, product_ids: List[int]) -> Dict[str, Dict[str, int]]:
        if not product_ids:
            return {}
        pipeline = [
            {"$match": {"product_id": {"$in": product_ids}}},
            {"$group": {"_id": {"aspect": "$aspect", "sentiment": "$sentiment"}, "count": {"$sum": 1}}},
        ]
        aspect_dict: Dict[str, Dict[str, int]] = {}
        for row in self.db.review_aspects.aggregate(pipeline, allowDiskUse=True):
            aspect = row["_id"].get("aspect")
            sentiment = (row["_id"].get("sentiment") or "neutral").lower()
            if not aspect:
                continue
            aspect_dict.setdefault(aspect, {"positive": 0, "negative": 0, "neutral": 0})
            aspect_dict[aspect][sentiment] = int(row["count"])
        return aspect_dict

    def bulk_upsert_reviews(self, batch_data: List[Dict[str, Any]]) -> Dict[str, int]:
        stats = {"inserted": 0, "updated": 0, "duplicated": 0, "failed": 0}
        if not batch_data:
            return stats
        now = utcnow()
        ops = []
        for row in batch_data:
            try:
                row = dict(row)
                has_source_created_at = row.get("created_at") is not None
                row.setdefault("id", next_sequence("reviews"))
                row.setdefault("review_language", "en")
                row.setdefault("review_like_count", 0)
                row.setdefault("created_at", now)
                row.setdefault("collected_at", now)
                row.setdefault("source", "")
                row.setdefault("platform_code", "")
                row.setdefault("external_product_id", "")
                row.setdefault("product_title", "")
                existing = self.db.reviews.find_one({"product_id": row["product_id"], "external_review_id": row["external_review_id"]}, {"id": 1})
                if existing:
                    stats["updated"] += 1
                    row.pop("id", None)
                    if not has_source_created_at:
                        row.pop("created_at", None)
                    ops.append(UpdateOne({"product_id": row["product_id"], "external_review_id": row["external_review_id"]}, {"$set": row}, upsert=False))
                else:
                    stats["inserted"] += 1
                    ops.append(UpdateOne({"product_id": row["product_id"], "external_review_id": row["external_review_id"]}, {"$setOnInsert": row}, upsert=True))
            except Exception:
                stats["failed"] += 1
        if ops:
            self.db.reviews.bulk_write(ops, ordered=False)
        return stats

    def add_review_aspects(self, aspects_data: List[Dict[str, Any]]) -> None:
        if not aspects_data:
            return
        now = utcnow()
        docs = []
        for item in aspects_data:
            doc = dict(item)
            doc.setdefault("id", next_sequence("review_aspects"))
            doc.setdefault("created_at", now)
            if "product_id" not in doc and "review_id" in doc:
                review = self.db.reviews.find_one({"id": doc["review_id"]}, {"product_id": 1})
                if review:
                    doc["product_id"] = review["product_id"]
            docs.append(doc)
        if docs:
            self.db.review_aspects.insert_many(docs, ordered=False)
