from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database
from app.db.database import get_db
from app.db.repositories.review_repo import ReviewRepository
from app.schemas.review import ReviewResponse

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.get("/{review_id}", response_model=ReviewResponse)
def get_review(review_id: int, db: Database = Depends(get_db)):
    review = ReviewRepository(db).get_by_id(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review
