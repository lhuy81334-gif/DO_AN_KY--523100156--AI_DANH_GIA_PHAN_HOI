from typing import List
from fastapi import APIRouter, Depends
from pymongo.database import Database
from app.db.database import get_db
from app.db.repositories.platform_repo import PlatformRepository
from app.schemas.platform import PlatformResponse

router = APIRouter(prefix="/platforms", tags=["Platforms"])


@router.get("", response_model=List[PlatformResponse])
def list_platforms(db: Database = Depends(get_db)):
    return PlatformRepository(db).get_all()
