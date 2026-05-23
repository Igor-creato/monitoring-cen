from fastapi import APIRouter, Depends, status

from app.api.deps import get_monitor_service
from app.api.v1.schemas.monitor import MonitorCreateRequest, MonitorResponse
from app.services.monitor_service import MonitorService

router = APIRouter()


@router.post("", response_model=MonitorResponse, status_code=status.HTTP_201_CREATED)
async def create_monitor(
    payload: MonitorCreateRequest,
    service: MonitorService = Depends(get_monitor_service),
) -> MonitorResponse:
    monitor = await service.create_monitor(payload)
    return MonitorResponse.model_validate(monitor)


@router.get("/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(
    monitor_id: int,
    service: MonitorService = Depends(get_monitor_service),
) -> MonitorResponse:
    monitor = await service.get_monitor(monitor_id)
    return MonitorResponse.model_validate(monitor)
