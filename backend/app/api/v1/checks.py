from fastapi import APIRouter, Depends

from app.api.deps import get_price_check_service
from app.api.v1.schemas.check import PriceCheckResponse
from app.services.price_check_service import PriceCheckService

router = APIRouter()


@router.post("/{monitor_id}/checks", response_model=PriceCheckResponse)
async def run_monitor_check(
    monitor_id: int,
    service: PriceCheckService = Depends(get_price_check_service),
) -> PriceCheckResponse:
    check = await service.run_check(monitor_id)
    return PriceCheckResponse.model_validate(check)
