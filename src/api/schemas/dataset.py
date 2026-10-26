from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    row_count: int
    file_size_bytes: int
    created_at: datetime


class DatasetUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)