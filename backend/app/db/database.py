import datetime
from types import SimpleNamespace
from typing import Any, Dict, Generator, Iterable, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from app.config import settings

client: MongoClient = MongoClient(settings.MONGODB_URL, serverSelectionTimeoutMS=3000)
db: Database = client[settings.MONGODB_DATABASE]


def get_db() -> Generator[Database, None, None]:
    yield db


def ping_database() -> bool:
    client.admin.command("ping")
    return True


def utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


def next_sequence(name: str) -> int:
    row = db.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return int(row["seq"])


def to_obj(document: Optional[Dict[str, Any]]) -> Optional[SimpleNamespace]:
    if document is None:
        return None
    clean = {k: v for k, v in document.items() if k != "_id"}
    return SimpleNamespace(**clean)


def to_objs(documents: Iterable[Dict[str, Any]]) -> list[SimpleNamespace]:
    return [to_obj(doc) for doc in documents if doc is not None]


def ensure_indexes(database: Database = db) -> None:
    database.platforms.create_index([("code", ASCENDING)], unique=True)

    database.shops.create_index([("platform_id", ASCENDING), ("external_shop_id", ASCENDING)], unique=True)
    database.shops.create_index([("id", DESCENDING)])

    database.products.create_index([("id", ASCENDING)], unique=True)
    database.products.create_index([("platform_id", ASCENDING), ("external_product_id", ASCENDING)], unique=True)
    database.products.create_index([("shop_id", ASCENDING)])
    database.products.create_index([("category", ASCENDING)])
    database.products.create_index([("rating", DESCENDING)])
    database.products.create_index([("review_count", DESCENDING)])
    database.products.create_index([("sold_count", DESCENDING)])
    database.products.create_index([("collected_at", DESCENDING)])
    database.products.create_index([("normalized_title", "text"), ("description", "text")])

    database.reviews.create_index([("id", ASCENDING)], unique=True)
    database.reviews.create_index([("product_id", ASCENDING), ("external_review_id", ASCENDING)], unique=True)
    database.reviews.create_index([("platform_code", ASCENDING), ("external_product_id", ASCENDING)])
    database.reviews.create_index([("source", ASCENDING)])
    database.reviews.create_index([("product_id", ASCENDING), ("rating", ASCENDING)])
    database.reviews.create_index([("created_at", DESCENDING)])

    database.review_aspects.create_index([("review_id", ASCENDING), ("aspect", ASCENDING), ("sentiment", ASCENDING)])
    database.review_aspects.create_index([("product_id", ASCENDING), ("aspect", ASCENDING), ("sentiment", ASCENDING)])

    database.review_trust_analyses.create_index([("review_id", ASCENDING)], unique=True)
    database.review_trust_analyses.create_index([("product_id", ASCENDING)])
    database.review_trust_analyses.create_index([("analysis.review_trust_score", DESCENDING)])

    database.ingestion_jobs.create_index([("job_id", ASCENDING)], unique=True)
