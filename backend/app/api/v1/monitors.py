from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import get_current_user, get_monitor_service
from app.api.v1.schemas.error import ErrorResponse
from app.api.v1.schemas.monitor import (
    MonitorCreateRequest,
    MonitorResponse,
    MonitorsListResponse,
    MonitorUpdateRequest,
)
from app.domain.enums import MonitorStatus
from app.infra.db.models.user import UserModel
from app.services.monitor_service import MonitorService

router = APIRouter()

ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Missing or invalid JWT"},
    404: {"model": ErrorResponse, "description": "Monitor not found"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


@router.post(
    "",
    response_model=MonitorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create monitor",
    description="Creates a price monitor for the authenticated user.",
    responses=ERROR_RESPONSES,
)
async def create_monitor(
    payload: MonitorCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    service: MonitorService = Depends(get_monitor_service),
) -> MonitorResponse:
    monitor = await service.create_monitor(current_user.id, payload)
    return MonitorResponse.model_validate(monitor)


@router.get(
    "",
    response_model=MonitorsListResponse,
    summary="List monitors",
    description="Returns paginated monitors owned by the authenticated user.",
    responses=ERROR_RESPONSES,
)
async def list_monitors(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    monitor_status: MonitorStatus | None = Query(default=None, alias="status"),
    current_user: UserModel = Depends(get_current_user),
    service: MonitorService = Depends(get_monitor_service),
) -> MonitorsListResponse:
    total, monitors = await service.list_monitors(
        current_user.id,
        limit,
        offset,
        monitor_status,
    )
    return MonitorsListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[MonitorResponse.model_validate(monitor) for monitor in monitors],
    )


@router.get(
    "/{monitor_id}",
    response_model=MonitorResponse,
    summary="Get monitor",
    description="Returns one monitor owned by the authenticated user.",
    responses=ERROR_RESPONSES,
)
async def get_monitor(
    monitor_id: int,
    current_user: UserModel = Depends(get_current_user),
    service: MonitorService = Depends(get_monitor_service),
) -> MonitorResponse:
    monitor = await service.get_monitor(current_user.id, monitor_id)
    return MonitorResponse.model_validate(monitor)


@router.patch(
    "/{monitor_id}",
    response_model=MonitorResponse,
    summary="Update monitor",
    description="Updates mutable monitor settings for the authenticated user.",
    responses=ERROR_RESPONSES,
)
async def update_monitor(
    monitor_id: int,
    payload: MonitorUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
    service: MonitorService = Depends(get_monitor_service),
) -> MonitorResponse:
    monitor = await service.update_monitor(current_user.id, monitor_id, payload)
    return MonitorResponse.model_validate(monitor)


@router.delete(
    "/{monitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete monitor",
    description="Soft-deletes a monitor owned by the authenticated user.",
    responses=ERROR_RESPONSES,
)
async def delete_monitor(
    monitor_id: int,
    current_user: UserModel = Depends(get_current_user),
    service: MonitorService = Depends(get_monitor_service),
) -> Response:
    await service.delete_monitor(current_user.id, monitor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
