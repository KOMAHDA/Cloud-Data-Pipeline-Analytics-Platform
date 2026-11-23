from pydantic import BaseModel


class PipelineValidationOut(BaseModel):
    pipeline_id: int
    is_valid: bool
    errors: list[str]
    supported_handlers: list[str]