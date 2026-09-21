from typing import List
from fastapi import APIRouter, Depends, Query
from pymongo.database import Database
from app.db.database import get_db
from app.db.repositories.shop_repo import ShopRepository
from app.schemas.shop import ShopResponse

router = APIRouter(prefix="/shops", tags=["Shops"])


@router.get("", response_model=List[ShopResponse])
def list_shops(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Database = Depends(get_db)):
    return ShopRepository(db).get_paginated(page=page, page_size=page_size)
