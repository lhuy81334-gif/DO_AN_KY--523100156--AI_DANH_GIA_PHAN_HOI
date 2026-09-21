import os
import shutil
import tempfile
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pymongo.database import Database

from app.db.database import get_db
from app.db.repositories.job_repo import JobRepository
from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.shop_repo import ShopRepository
from app.schemas.dataset import JobStatusResponse
from app.services.seller_feedback import seller_attention_query
from app.services.job_service import JobService

router = APIRouter(prefix="/datasets", tags=["Datasets & Import"])


@router.post("/import/products")
async def import_products_dataset(background_tasks: BackgroundTasks, file: UploadFile = File(...), platform_code: str = Query("tiki"), sync: bool = Query(False), db: Database = Depends(get_db)):
    if not file.filename or not (file.filename.endswith(".csv") or file.filename.endswith(".json")):
        raise HTTPException(status_code=400, detail="Only .csv and .json files are supported")
    saved_path = os.path.join(tempfile.gettempdir(), f"upload_prod_{file.filename}")
    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    job_id = JobService.start_import_job(saved_path, job_type="products", platform_code=platform_code)
    if sync:
        JobService.run_import_task(job_id, saved_path, job_type="products", platform_code=platform_code)
        job = JobRepository(db).get_by_job_id(job_id)
        return {"job_id": job_id, "status": job.status, "total_rows": job.total_rows, "inserted": job.inserted_count, "updated": job.updated_count, "duplicated": job.duplicated_count, "failed": job.failed_count}
    background_tasks.add_task(JobService.run_import_task, job_id, saved_path, "products", platform_code)
    return {"job_id": job_id, "status": "QUEUED", "message": "Import job has been queued in the background."}


@router.post("/import/reviews")
async def import_reviews_dataset(background_tasks: BackgroundTasks, file: UploadFile = File(...), platform_code: str = Query("tiki"), sync: bool = Query(False), db: Database = Depends(get_db)):
    if not file.filename or not (file.filename.endswith(".csv") or file.filename.endswith(".json")):
        raise HTTPException(status_code=400, detail="Only .csv and .json files are supported")
    saved_path = os.path.join(tempfile.gettempdir(), f"upload_rev_{file.filename}")
    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    job_id = JobService.start_import_job(saved_path, job_type="reviews", platform_code=platform_code)
    if sync:
        JobService.run_import_task(job_id, saved_path, job_type="reviews", platform_code=platform_code)
        job = JobRepository(db).get_by_job_id(job_id)
        return {"job_id": job_id, "status": job.status, "total_rows": job.total_rows, "inserted": job.inserted_count, "updated": job.updated_count, "duplicated": job.duplicated_count, "failed": job.failed_count}
    background_tasks.add_task(JobService.run_import_task, job_id, saved_path, "reviews", platform_code)
    return {"job_id": job_id, "status": "QUEUED", "message": "Import job has been queued in the background."}


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Database = Depends(get_db)):
    job = JobRepository(db).get_by_job_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/overview")
def get_dataset_overview(
    platform_code: Optional[str] = Query(None),
    external_product_id: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    db: Database = Depends(get_db),
):
    review_query = {}
    product_query = {}
    if platform_code:
        review_query["platform_code"] = platform_code
        platform = PlatformRepository(db).get_by_code(platform_code)
        if platform:
            product_query["platform_id"] = platform.id
        else:
            product_query["platform_id"] = -1
    if external_product_id:
        review_query["external_product_id"] = external_product_id
        product_query["external_product_id"] = external_product_id
    if product_id is not None:
        review_query["product_id"] = product_id
        product_query["id"] = product_id

    attention_query = seller_attention_query(review_query)
    return {
        "total_products": db.products.count_documents(product_query),
        "total_reviews": db.reviews.count_documents(review_query),
        "total_shops": ShopRepository(db).get_total_count(),
        "total_reviews_with_images": db.reviews.count_documents({**review_query, "image_urls.0": {"$exists": True}}),
        "total_reviews_need_seller_attention": db.reviews.count_documents(attention_query),
        "total_review_trust_analyses": db.reviews.count_documents({**review_query, "trust_analysis": {"$exists": True}}),
    }
