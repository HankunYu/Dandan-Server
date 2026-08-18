import asyncio
import logging
from datetime import datetime, timedelta, UTC
from typing import Optional

from sqlalchemy import delete, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.api_stats import ApiStats

logger = logging.getLogger(__name__)

# Small batches keep each DELETE transaction short so request handlers
# are never stuck on the SQLite write lock for long
PURGE_BATCH_SIZE = 50_000
PURGE_BATCH_PAUSE_SECONDS = 0.5
PURGE_INTERVAL_SECONDS = 24 * 60 * 60

_worker_task: Optional[asyncio.Task] = None


async def purge_expired_stats() -> int:
    """Delete api_stats rows older than API_STATS_RETENTION_DAYS, in batches."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.API_STATS_RETENTION_DAYS)
    total = 0
    while True:
        async with AsyncSessionLocal() as session:
            expired_ids = (
                select(ApiStats.id)
                .where(ApiStats.timestamp < cutoff)
                .limit(PURGE_BATCH_SIZE)
                .scalar_subquery()
            )
            result = await session.execute(
                delete(ApiStats).where(ApiStats.id.in_(expired_ids))
            )
            await session.commit()
        deleted = result.rowcount or 0
        total += deleted
        if deleted < PURGE_BATCH_SIZE:
            break
        # Yield between batches so normal writes interleave with the purge
        await asyncio.sleep(PURGE_BATCH_PAUSE_SECONDS)
    if total:
        logger.info(
            f"api_stats清理完成: 删除{total}行, 保留最近{settings.API_STATS_RETENTION_DAYS}天"
        )
    return total


async def _retention_worker() -> None:
    """Purge expired stats on startup, then once a day."""
    logger.info(
        f"api_stats清理任务已启动: 保留{settings.API_STATS_RETENTION_DAYS}天, 每24小时清理一次"
    )
    while True:
        try:
            await purge_expired_stats()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"api_stats清理失败: {e}")
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)


def start_retention_worker() -> None:
    """Start the retention task (called on app startup); disabled when retention is 0."""
    global _worker_task
    if settings.API_STATS_RETENTION_DAYS <= 0:
        return
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_retention_worker())


async def stop_retention_worker() -> None:
    """Stop the retention task (called on app shutdown)."""
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
