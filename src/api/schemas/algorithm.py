from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AlgorithmCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    grpc_handler: str = Field(min_length=1, max_length=255)
    default_params: dict = Field(default_factory=dict)


class AlgorithmUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    grpc_handler: Optional[str] = Field(default=None, min_length=1, max_length=255)
    default_params: Optional[dict] = None
    is_active: Optional[bool] = None


class AlgorithmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str]
    grpc_handler: str
    default_params: dict
    is_active: bool
    created_at: datetime