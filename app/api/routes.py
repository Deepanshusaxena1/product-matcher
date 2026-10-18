import logging
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import CompareRequest, ErrorResponse, HealthResponse
from app.domain.models import ComparisonEvent, ComparisonReport
from app.domain.ports import ProductComparer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Amazon has no product at that link."},
    422: {"model": ErrorResponse, "description": "Not an Amazon.in product link, or unsupported category."},
    502: {"model": ErrorResponse, "description": "Amazon could not be read."},
}
_STREAM_FAILED = ErrorResponse(code="stream_failed", detail="Something went wrong while checking. Try again.")


def get_comparer(request: Request) -> ProductComparer:
    return cast("ProductComparer", request.app.state.comparer)


@router.post(
    "/compare",
    response_model=ComparisonReport,
    responses=_ERRORS,
    summary="Find the Amazon product on the other platforms",
)
async def compare(
    body: CompareRequest, comparer: Annotated[ProductComparer, Depends(get_comparer)]
) -> ComparisonReport:
    return await comparer.compare(body.url)


@router.post(
    "/compare/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "Server-sent events: `source`, then one `result` per platform as each finishes, "
            "then `done` (or `error` if something broke midway).",
        },
        **_ERRORS,
    },
    summary="The same comparison, sent shop by shop as each one answers",
)
async def compare_stream(
    body: CompareRequest, comparer: Annotated[ProductComparer, Depends(get_comparer)]
) -> StreamingResponse:
    events = comparer.stream(body.url)
    # Problems with the link surface here, before streaming starts, as ordinary HTTP errors.
    first = await anext(events)
    return StreamingResponse(
        _server_sent_events(first, events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # no proxy buffering
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


async def _server_sent_events(
    first: ComparisonEvent, rest: AsyncGenerator[ComparisonEvent, None]
) -> AsyncIterator[str]:
    try:
        yield _frame(first.kind, first.model_dump_json())
        async for event in rest:
            yield _frame(event.kind, event.model_dump_json())
        yield _frame("done", "{}")
    except Exception:  # the response has started, so the failure can only be reported in the stream
        logger.exception("comparison stream failed")
        yield _frame("error", _STREAM_FAILED.model_dump_json())
    finally:
        await rest.aclose()  # stops any shop still being checked, e.g. when the browser went away


def _frame(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"
