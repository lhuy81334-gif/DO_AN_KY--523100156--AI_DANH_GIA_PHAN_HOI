import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, ConfigDict


class ReviewBase(BaseModel):
    product_id: int
    external_review_id: str
    rating: float
    review_text: str
    review_language: str = "en"
    review_like_count: int = 0


class ReviewCreate(ReviewBase):
    pass


class ReviewAspectResponse(BaseModel):
    id: int
    aspect: str
    sentiment: str
    confidence: float

    model_config = ConfigDict(from_attributes=True)


class ReviewResponse(ReviewBase):
    id: int
    created_at: datetime.datetime
    collected_at: datetime.datetime
    aspects: List[ReviewAspectResponse] = []

    model_config = ConfigDict(from_attributes=True)


class PaginatedReviewsResponse(BaseModel):
    items: List[ReviewResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AspectSentimentCount(BaseModel):
    positive: int = 0
    negative: int = 0
    neutral: int = 0


class ProductAspectSummaryResponse(BaseModel):
    product_id: int
    aspects: Dict[str, AspectSentimentCount]
    total_reviews_analyzed: int
