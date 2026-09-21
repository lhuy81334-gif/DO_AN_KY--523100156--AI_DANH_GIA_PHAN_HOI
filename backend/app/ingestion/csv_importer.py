import logging
from typing import Any, Callable, Dict, Optional

import pandas as pd
from pymongo.database import Database

from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.product_repo import ProductRepository
from app.db.repositories.review_repo import ReviewRepository
from app.ingestion.normalizer import DataNormalizer
from app.ml.sentiment import extract_aspect_sentiments

logger = logging.getLogger(__name__)


class CSVImporter:
    def __init__(self, db: Database, batch_size: int = 1000):
        self.db = db
        self.batch_size = batch_size
        self.platform_repo = PlatformRepository(db)
        self.product_repo = ProductRepository(db)
        self.review_repo = ReviewRepository(db)

    def import_products_file(self, file_path: str, platform_code: str = "tiki", progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict[str, int]:
        stats = {"total_rows": 0, "inserted": 0, "updated": 0, "duplicated": 0, "failed": 0}
        platform = self.platform_repo.get_or_create(platform_code, platform_code.capitalize())
        try:
            stats["total_rows"] = max(0, sum(1 for _ in open(file_path, "r", encoding="utf-8", errors="ignore")) - 1)
        except Exception:
            pass
        processed = 0
        for chunk in pd.read_csv(file_path, chunksize=self.batch_size, dtype=str):
            chunk = chunk.fillna("")
            batch_data = []
            for _, row in chunk.iterrows():
                try:
                    norm = DataNormalizer.normalize_product(row.to_dict(), platform_id=platform.id)
                    if norm["title"] and norm["external_product_id"]:
                        batch_data.append(norm)
                    else:
                        stats["failed"] += 1
                except Exception:
                    stats["failed"] += 1
            if batch_data:
                chunk_stats = self.product_repo.bulk_upsert_products(batch_data)
                for key in ["inserted", "updated", "duplicated", "failed"]:
                    stats[key] += chunk_stats[key]
            processed += len(chunk)
            if progress_callback:
                progress_callback(processed, stats["total_rows"])
        return stats

    def import_reviews_file(self, file_path: str, platform_code: str = "tiki", progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict[str, int]:
        stats = {"total_rows": 0, "inserted": 0, "updated": 0, "duplicated": 0, "failed": 0}
        platform = self.platform_repo.get_or_create(platform_code, platform_code.capitalize())
        try:
            stats["total_rows"] = max(0, sum(1 for _ in open(file_path, "r", encoding="utf-8", errors="ignore")) - 1)
        except Exception:
            pass
        processed = 0
        for chunk in pd.read_csv(file_path, chunksize=self.batch_size, dtype=str):
            chunk = chunk.fillna("")
            batch_reviews = []
            for _, row in chunk.iterrows():
                try:
                    row_dict = row.to_dict()
                    ext_prod_id = str(row_dict.get("external_product_id") or row_dict.get("product_id") or "")
                    prod = self.product_repo.get_by_external_id(platform.id, ext_prod_id)
                    if not prod:
                        stats["failed"] += 1
                        continue
                    norm_rev = DataNormalizer.normalize_review(row_dict, product_id=prod.id)
                    if norm_rev["review_text"] and norm_rev["external_review_id"]:
                        batch_reviews.append(norm_rev)
                    else:
                        stats["failed"] += 1
                except Exception:
                    stats["failed"] += 1
            inserted_before = stats["inserted"]
            if batch_reviews:
                chunk_stats = self.review_repo.bulk_upsert_reviews(batch_reviews)
                for key in ["inserted", "updated", "duplicated", "failed"]:
                    stats[key] += chunk_stats[key]
                self._create_aspects_for_reviews(batch_reviews)
            processed += len(chunk)
            if progress_callback:
                progress_callback(processed, stats["total_rows"])
        return stats

    def _create_aspects_for_reviews(self, reviews: list[Dict[str, Any]]) -> None:
        aspects = []
        for review in reviews:
            saved = self.db.reviews.find_one({"product_id": review["product_id"], "external_review_id": review["external_review_id"]}, {"id": 1})
            if not saved:
                continue
            self.db.review_aspects.delete_many({"review_id": saved["id"]})
            for aspect in extract_aspect_sentiments(review["review_text"]):
                aspects.append({"review_id": saved["id"], "product_id": review["product_id"], **aspect})
        self.review_repo.add_review_aspects(aspects)
