from typing import List, Optional
from pymongo.database import Database
from app.db.database import next_sequence, to_obj, to_objs, utcnow


class PlatformRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_by_id(self, platform_id: int):
        return to_obj(self.db.platforms.find_one({"id": platform_id}))

    def get_by_code(self, code: str):
        return to_obj(self.db.platforms.find_one({"code": code}))

    def get_all(self) -> List:
        return to_objs(self.db.platforms.find().sort("id", 1))

    def get_or_create(self, code: str, name: str):
        existing = self.get_by_code(code)
        if existing:
            return existing
        now = utcnow()
        doc = {"id": next_sequence("platforms"), "code": code, "name": name, "created_at": now}
        self.db.platforms.insert_one(doc)
        return to_obj(doc)
