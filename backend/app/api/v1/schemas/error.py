from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code")
    message: str = Field(description="Human-readable error message")
    details: Any | None = Field(default=None, description="Optional structured details")
    request_id: str | None = Field(default=None, description="Request id, when available")


class ErrorResponse(BaseModel):
    error: ErrorBody
