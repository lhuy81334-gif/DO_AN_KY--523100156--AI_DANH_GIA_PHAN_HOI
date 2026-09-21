import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class ProductBase(BaseModel):
    platform_id: int
    shop_id: Optional[int] = None
    external_product_id: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: float = 0.0
    currency: str = "USD"
    rating: float = 0.0
    review_count: int = 0
    sold_count: int = 0
    product_url: Optional[str] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    sold_count: Optional[int] = None


class ProductResponse(ProductBase):
    id: int
    normalized_title: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    collected_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedProductsResponse(BaseModel):
    items: List[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
