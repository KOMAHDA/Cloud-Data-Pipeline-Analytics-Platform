from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

JobStatus = Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]


class JobCreate(BaseModel):
    dataset_id: int
    pipeline_id: int


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    dataset_id: int
    pipeline_id: int
    status: str
    current_step: int
    created_at: datetime
    finished_at: datetime | None = None


class JobResultOut(BaseModel):
    job_id: int
    status: str
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None


class JobStatusUpdate(BaseModel):
    status: JobStatus
    current_step: int = 0
    result_data: dict[str, Any] | None = None