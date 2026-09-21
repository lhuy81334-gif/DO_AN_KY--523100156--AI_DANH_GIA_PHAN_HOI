from typing import List, Optional
from pymongo.database import Database
from app.db.database import next_sequence, to_obj, to_objs, utcnow


class ShopRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_by_id(self, shop_id: int):
        return to_obj(self.db.shops.find_one({"id": shop_id}))

    def get_by_external_id(self, platform_id: int, external_shop_id: str):
        return to_obj(self.db.shops.find_one({"platform_id": platform_id, "external_shop_id": external_shop_id}))

    def get_or_create(self, platform_id: int, external_shop_id: str, shop_name: str):
        existing = self.get_by_external_id(platform_id, external_shop_id)
        if existing:
            return existing
        now = utcnow()
        doc = {
            "id": next_sequence("shops"),
            "platform_id": platform_id,
            "external_shop_id": external_shop_id,
            "shop_name": shop_name,
            "shop_rating": 0.0,
            "review_count": 0,
            "sold_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.db.shops.insert_one(doc)
        return to_obj(doc)

    def get_total_count(self) -> int:
        return self.db.shops.count_documents({})

    def get_paginated(self, page: int = 1, page_size: int = 20) -> List:
        skip = (page - 1) * page_size
        return to_objs(self.db.shops.find().sort("id", -1).skip(skip).limit(page_size))
