import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class PlatformBase(BaseModel):
    name: str
    code: str


class PlatformCreate(PlatformBase):
    pass


class PlatformResponse(PlatformBase):
    id: int
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)
