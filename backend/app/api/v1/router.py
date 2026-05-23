from fastapi import APIRouter

from app.api.v1 import auth, internal, monitors, products

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(monitors.router, prefix="/monitors", tags=["monitors"])
router.include_router(products.router, prefix="/products", tags=["products"])
router.include_router(internal.router, prefix="/internal", tags=["internal"])
