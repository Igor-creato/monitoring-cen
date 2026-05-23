from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_product_service
from app.api.v1.schemas.error import ErrorResponse
from app.api.v1.schemas.product import PriceHistoryItem, ProductHistoryResponse
from app.infra.db.models.user import UserModel
from app.services.product_service import ProductService

router = APIRouter()


@router.get(
    "/{product_id}/history",
    response_model=ProductHistoryResponse,
    summary="Get product price history",
    description="Returns historical price check records for a product.",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid JWT"},
        404: {"model": ErrorResponse, "description": "Product not found"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def get_product_history(
    product_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: UserModel = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
) -> ProductHistoryResponse:
    total, checks = await service.get_history(current_user.id, product_id, limit, offset)
    return ProductHistoryResponse(
        product_id=product_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[PriceHistoryItem.model_validate(check) for check in checks],
    )
