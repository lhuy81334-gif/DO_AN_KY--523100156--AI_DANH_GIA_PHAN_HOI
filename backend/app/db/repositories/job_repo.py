from typing import Optional
from pymongo.database import Database
from app.db.database import next_sequence, to_obj, utcnow


class JobRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_job(self, job_id: str, job_type: str, file_name: str):
        now = utcnow()
        doc = {
            "id": next_sequence("ingestion_jobs"),
            "job_id": job_id,
            "job_type": job_type,
            "file_name": file_name,
            "status": "QUEUED",
            "total_rows": 0,
            "processed_rows": 0,
            "inserted_count": 0,
            "updated_count": 0,
            "duplicated_count": 0,
            "failed_count": 0,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        self.db.ingestion_jobs.insert_one(doc)
        return to_obj(doc)

    def get_by_job_id(self, job_id: str):
        return to_obj(self.db.ingestion_jobs.find_one({"job_id": job_id}))

    def update_progress(self, job_id: str, processed_rows: int, total_rows: int):
        self.db.ingestion_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "PROCESSING", "processed_rows": processed_rows, "total_rows": total_rows, "updated_at": utcnow()}},
        )

    def complete_job(self, job_id: str, total_rows: int, inserted: int, updated: int, duplicated: int, failed: int):
        self.db.ingestion_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "COMPLETED", "total_rows": total_rows, "processed_rows": total_rows, "inserted_count": inserted, "updated_count": updated, "duplicated_count": duplicated, "failed_count": failed, "updated_at": utcnow()}},
        )

    def fail_job(self, job_id: str, error_message: str):
        self.db.ingestion_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "FAILED", "error_message": error_message, "updated_at": utcnow()}},
        )
