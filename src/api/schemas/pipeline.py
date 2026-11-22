from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class PipelineStepIn(BaseModel):
    algorithm_id: int
    step_order: int = Field(ge=1)
    step_params: dict = Field(default_factory=dict)


class PipelineCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    steps: List[PipelineStepIn] = Field(min_length=1)


class PipelineUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    steps: Optional[List[PipelineStepIn]] = Field(default=None, min_length=1)


class AlgorithmBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class PipelineStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_order: int
    step_params: dict
    algorithm: AlgorithmBrief


class PipelineSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str]
    is_published: bool
    created_by: Optional[int]
    created_at: datetime


class PipelineOut(PipelineSummary):
    steps: List[PipelineStepOut]