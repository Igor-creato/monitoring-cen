from typing import Any

from app.workers.tasks import run_due_monitor_checks


async def schedule_due_checks(ctx: dict[str, Any]) -> None:
    await run_due_monitor_checks(ctx)
