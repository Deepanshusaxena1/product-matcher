"""Translate domain errors into HTTP responses. Adding an error type means adding one row to the table."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from app.api.schemas import ErrorResponse
from app.domain.errors import (
    InvalidProductUrlError,
    MatcherError,
    ProductNotFoundError,
    SourceUnavailableError,
    UnsupportedCategoryError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fastapi import FastAPI, Request

_HTTP_STATUS: Mapping[type[MatcherError], int] = MappingProxyType(
    {
        InvalidProductUrlError: 422,
        UnsupportedCategoryError: 422,
        ProductNotFoundError: 404,
        SourceUnavailableError: 502,
    }
)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(MatcherError, _matcher_error_response)


async def _matcher_error_response(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, MatcherError)  # registered for MatcherError only
    body = ErrorResponse(code=error.code, detail=error.message)
    return JSONResponse(status_code=_status_for(error), content=body.model_dump())


def _status_for(error: MatcherError) -> int:
    for error_type in type(error).__mro__:
        if error_type in _HTTP_STATUS:
            return _HTTP_STATUS[error_type]
    return 500
