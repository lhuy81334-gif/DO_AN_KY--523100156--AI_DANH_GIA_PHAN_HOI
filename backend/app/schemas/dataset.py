import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    file_name: Optional[str] = None
    status: str
    total_rows: int = 0
    processed_rows: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    duplicated_count: int = 0
    failed_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ImportStatsResponse(BaseModel):
    total_rows: int
    inserted: int
    updated: int
    duplicated: int
    failed: int
    job_id: Optional[str] = None
