from fastapi import APIRouter

from app.api.v1 import checks, monitors

router = APIRouter()
router.include_router(monitors.router, prefix="/monitors", tags=["monitors"])
router.include_router(checks.router, prefix="/monitors", tags=["checks"])
