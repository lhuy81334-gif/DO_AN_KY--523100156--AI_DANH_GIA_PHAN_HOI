import logging
import os
import uuid

from app.db.database import db
from app.db.repositories.job_repo import JobRepository
from app.ingestion.csv_importer import CSVImporter
from app.ingestion.json_importer import JSONImporter

logger = logging.getLogger(__name__)


class JobService:
    @staticmethod
    def start_import_job(file_path: str, job_type: str, platform_code: str = "tiki") -> str:
        job_id = str(uuid.uuid4())
        JobRepository(db).create_job(job_id=job_id, job_type=job_type, file_name=os.path.basename(file_path))
        return job_id

    @staticmethod
    def run_import_task(job_id: str, file_path: str, job_type: str, platform_code: str = "tiki") -> None:
        job_repo = JobRepository(db)
        try:
            is_csv = file_path.lower().endswith(".csv")

            def on_progress(processed: int, total: int):
                job_repo.update_progress(job_id, processed_rows=processed, total_rows=total)

            importer = CSVImporter(db, batch_size=1000) if is_csv else JSONImporter(db, batch_size=1000)
            if job_type == "products":
                stats = importer.import_products_file(file_path, platform_code=platform_code, progress_callback=on_progress)
            else:
                stats = importer.import_reviews_file(file_path, platform_code=platform_code, progress_callback=on_progress)

            job_repo.complete_job(
                job_id=job_id,
                total_rows=stats["total_rows"],
                inserted=stats["inserted"],
                updated=stats["updated"],
                duplicated=stats["duplicated"],
                failed=stats["failed"],
            )
            logger.info(f"Import job {job_id} completed: {stats}")
        except Exception as e:
            logger.error(f"Import job {job_id} failed: {e}", exc_info=True)
            job_repo.fail_job(job_id=job_id, error_message=str(e))
