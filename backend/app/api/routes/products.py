import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database
from app.db.database import get_db
from app.db.repositories.product_repo import ProductRepository
from app.db.repositories.review_repo import ReviewRepository
from app.schemas.product import PaginatedProductsResponse, ProductResponse
from app.schemas.review import AspectSentimentCount, PaginatedReviewsResponse, ProductAspectSummaryResponse

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=PaginatedProductsResponse)
def get_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    platform_id: Optional[int] = Query(None),
    db: Database = Depends(get_db),
):
    items, total = ProductRepository(db).get_paginated(page=page, page_size=page_size, search=search, category=category, platform_id=platform_id)
    return PaginatedProductsResponse(items=items, total=total, page=page, page_size=page_size, total_pages=math.ceil(total / page_size) if total > 0 else 1)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product_detail(product_id: int, db: Database = Depends(get_db)):
    product = ProductRepository(db).get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/{product_id}/reviews", response_model=PaginatedReviewsResponse)
def get_product_reviews(
    product_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    rating: Optional[float] = Query(None),
    db: Database = Depends(get_db),
):
    if not ProductRepository(db).get_by_id(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    items, total = ReviewRepository(db).get_paginated_by_product(product_id=product_id, page=page, page_size=page_size, rating=rating)
    return PaginatedReviewsResponse(items=items, total=total, page=page, page_size=page_size, total_pages=math.ceil(total / page_size) if total > 0 else 1)


@router.get("/{product_id}/aspects", response_model=ProductAspectSummaryResponse)
def get_product_aspect_summary(product_id: int, db: Database = Depends(get_db)):
    if not ProductRepository(db).get_by_id(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    agg = ReviewRepository(db).get_aspect_sentiment_aggregations([product_id])
    aspects_res = {}
    total_analyzed = 0
    for aspect, counts in agg.items():
        aspects_res[aspect] = AspectSentimentCount(positive=counts.get("positive", 0), negative=counts.get("negative", 0), neutral=counts.get("neutral", 0))
        total_analyzed += counts.get("positive", 0) + counts.get("negative", 0) + counts.get("neutral", 0)
    return ProductAspectSummaryResponse(product_id=product_id, aspects=aspects_res, total_reviews_analyzed=total_analyzed)
