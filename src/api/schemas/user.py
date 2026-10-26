from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    created_at: datetime


class UserRoleUpdate(BaseModel):
    role: Literal["ADMIN", "CLIENT"]