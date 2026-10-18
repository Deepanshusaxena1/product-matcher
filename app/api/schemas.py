"""Request and response bodies that are specific to HTTP (domain models are returned as they are)."""

from pydantic import BaseModel, Field


class CompareRequest(BaseModel):
    url: str = Field(
        min_length=1,
        max_length=2048,
        description="An Amazon.in product link, or shared text that contains one.",
        examples=["https://www.amazon.in/dp/B0DHL7YT5S"],
    )


class ErrorResponse(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    detail: str = Field(description="What went wrong, in words fit to show the user.")


class HealthResponse(BaseModel):
    status: str
