from fastapi import APIRouter, Depends, status

from app.api.deps import get_price_check_service, require_internal_token
from app.api.v1.schemas.check import PriceCheckResponse
from app.api.v1.schemas.error import ErrorResponse
from app.services.price_check_service import PriceCheckService

router = APIRouter()


@router.post(
    "/check-monitor/{monitor_id}",
    response_model=PriceCheckResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run monitor check",
    description=(
        "Internal endpoint for scheduler/worker integrations. "
        "Requires X-Internal-Token when INTERNAL_API_TOKEN is configured."
    ),
    responses={
        403: {"model": ErrorResponse, "description": "Invalid internal token"},
        404: {"model": ErrorResponse, "description": "Monitor not found"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def check_monitor(
    monitor_id: int,
    _: None = Depends(require_internal_token),
    service: PriceCheckService = Depends(get_price_check_service),
) -> PriceCheckResponse:
    check = await service.run_check(monitor_id)
    return PriceCheckResponse.model_validate(check)
