import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ShopBase(BaseModel):
    platform_id: int
    external_shop_id: str
    shop_name: str
    shop_rating: float = 0.0
    review_count: int = 0
    sold_count: int = 0


class ShopCreate(ShopBase):
    pass


class ShopResponse(ShopBase):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)
