"""Standard error response schema for Dolores services."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    retry_after: int | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error_response(code: str, message: str, status_code: int = 500, retry_after: int | None = None) -> JSONResponse:
    """Create a standardized error JSON response."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=ErrorDetail(code=code, message=message, retry_after=retry_after)
        ).model_dump(),
    )


async def service_unavailable_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle 503 errors with standard format."""
    return error_response(
        code="service_unavailable",
        message=str(exc.detail),
        status_code=503,
        retry_after=5,
    )
