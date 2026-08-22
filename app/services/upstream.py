import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Set

import httpx
from sqlalchemy import select

from ..config import settings
from .signature import generate_signature

# 配置日志记录器
logger = logging.getLogger(__name__)

DANMAKU_COOLDOWN_PREFIX = "danmaku:"
# 配额熔断按上游功能组独立进行：上游返回"已达到接口调用配额上限"(body errorCode=429)时
# 只熔断对应功能组，其余组照常回源（弹弹play按功能组分别计配额）
QUOTA_GROUP_MATCH = "match"      # 文件识别 /api/v2/match
QUOTA_GROUP_SEARCH = "search"    # 搜索 /api/v2/search/*
QUOTA_GROUP_COMMENT = "comment"  # 获取弹幕 /api/v2/comment/*
QUOTA_GROUPS = (QUOTA_GROUP_MATCH, QUOTA_GROUP_SEARCH, QUOTA_GROUP_COMMENT)
_QUOTA_COOLDOWN_PREFIX = "upstream:quota:"

# ---------------------------------------------------------------------------
# 运行时指标：进程内计数器，供监控面板展示后端工作状态
# ---------------------------------------------------------------------------
STARTED_AT = datetime.now()

metrics: Dict[str, int] = {
    "upstream_requests": 0,       # 发往上游的请求总数
    "upstream_429": 0,            # 上游HTTP 429次数
    "quota_breaker_trips": 0,     # 全局配额熔断触发次数
    "danmaku_cache_hit": 0,       # 弹幕新鲜缓存命中
    "danmaku_stale_served": 0,    # 弹幕过期缓存兜底
    "danmaku_cold_fetch": 0,      # 弹幕冷启动同步回源
    "danmaku_blocked": 0,         # 弹幕冷却/熔断期被拒(503)
    "match_cache_hit": 0,         # match正缓存命中
    "match_negative_hit": 0,      # match负缓存命中
    "match_upstream": 0,          # match回源
    "ip_budget_blocked": 0,       # 超出单IP每日回源预算被拒(429)
    "tmdb_cache_hit": 0,          # tmdb缓存命中
    "tmdb_upstream": 0,           # tmdb回源
    "refresh_done": 0,            # 后台刷新成功
    "refresh_fail": 0,            # 后台刷新失败
}


def inc_metric(key: str, n: int = 1) -> None:
    """递增一个运行时计数器"""
    metrics[key] = metrics.get(key, 0) + n


def runtime_status() -> Dict[str, Any]:
    """汇总当前运行时状态，供监控面板使用"""
    now = time.monotonic()
    return {
        "started_at": STARTED_AT.isoformat(),
        "uptime_seconds": int((datetime.now() - STARTED_AT).total_seconds()),
        "quota_breakers": {g: int(quota_cooldown_remaining(g)) for g in QUOTA_GROUPS},
        "active_cooldowns": sum(1 for v in _cooldowns.values() if v > now),
        "refresh_queue_size": _refresh_queue.qsize(),
        "refresh_pending": len(_refresh_pending),
        "inflight_requests": len(_inflight),
        "metrics": dict(metrics),
    }


def quota_cooldown_remaining(group: str) -> float:
    """该功能组配额熔断剩余秒数，未熔断返回0"""
    return cooldown_remaining(f"{_QUOTA_COOLDOWN_PREFIX}{group}")


def trip_quota_breaker(group: str) -> None:
    """触发指定功能组的配额熔断"""
    if quota_cooldown_remaining(group) <= 0:
        set_cooldown(f"{_QUOTA_COOLDOWN_PREFIX}{group}", settings.QUOTA_COOLDOWN_MINUTES)
        inc_metric("quota_breaker_trips")
        logger.warning(f"上游[{group}]配额已耗尽，熔断{settings.QUOTA_COOLDOWN_MINUTES}分钟")

# ---------------------------------------------------------------------------
# 共享HTTP客户端（模块级单例，跨请求复用连接池）
# ---------------------------------------------------------------------------
_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """获取共享的HTTP客户端"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _client


async def close_client() -> None:
    """关闭共享HTTP客户端（应用关闭时调用）"""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


# ---------------------------------------------------------------------------
# 全局节流：限制上游并发数 + 强制请求最小间隔，把突发流量摊平成匀速
# ---------------------------------------------------------------------------
_semaphore = asyncio.Semaphore(settings.UPSTREAM_MAX_CONCURRENCY)
_interval_lock = asyncio.Lock()
_last_request_at = 0.0


async def throttled_request(method: str, url: str, **kwargs) -> httpx.Response:
    """所有上游请求统一经过的节流入口"""
    global _last_request_at
    min_interval = settings.UPSTREAM_MIN_INTERVAL_MS / 1000.0
    async with _semaphore:
        async with _interval_lock:
            wait = _last_request_at + min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            _last_request_at = time.monotonic()
        inc_metric("upstream_requests")
        response = await get_client().request(method, url, **kwargs)
        if response.status_code == 429:
            inc_metric("upstream_429")
        return response


# ---------------------------------------------------------------------------
# 失败冷却（负缓存）：被上游429的key在冷却期内不再回源，打断重试风暴
# ---------------------------------------------------------------------------
_cooldowns: Dict[str, float] = {}


def set_cooldown(key: str, minutes: Optional[float] = None) -> None:
    """记录一个失败冷却，冷却期内 cooldown_remaining 返回剩余秒数"""
    duration = (minutes if minutes is not None else settings.FAILURE_COOLDOWN_MINUTES) * 60
    _cooldowns[key] = time.monotonic() + duration
    # 防止字典无限增长，超过阈值时清理已过期条目
    if len(_cooldowns) > 10000:
        now = time.monotonic()
        for stale_key in [k for k, v in _cooldowns.items() if v <= now]:
            del _cooldowns[stale_key]


def cooldown_remaining(key: str) -> float:
    """返回冷却剩余秒数，未在冷却中返回0"""
    until = _cooldowns.get(key)
    if until is None:
        return 0.0
    remaining = until - time.monotonic()
    if remaining <= 0:
        _cooldowns.pop(key, None)
        return 0.0
    return remaining


# ---------------------------------------------------------------------------
# Single-flight：相同key的并发请求只回源一次，其余请求等待同一个结果
# ---------------------------------------------------------------------------
_inflight: Dict[str, asyncio.Future] = {}


async def single_flight(key: str, factory: Callable[[], Awaitable[Any]]) -> Any:
    """合并相同key的并发调用，同一时刻每个key只执行一次factory"""
    existing = _inflight.get(key)
    if existing is not None:
        return await asyncio.shield(existing)

    future = asyncio.get_running_loop().create_future()
    _inflight[key] = future
    try:
        result = await factory()
        future.set_result(result)
        return result
    except BaseException as e:
        future.set_exception(e)
        # 没有等待者时主动取回异常，避免asyncio的"never retrieved"警告
        future.exception()
        raise
    finally:
        _inflight.pop(key, None)


# ---------------------------------------------------------------------------
# 弹幕回源：从上游获取并写入缓存（使用独立数据库会话，可在后台任务中调用）
# ---------------------------------------------------------------------------
async def fetch_and_cache_danmaku(
    episode_id: int,
    from_id: int = 0,
    with_related: bool = True,
    ch_convert: int = 0,
) -> Dict[str, Any]:
    """从弹弹play获取弹幕并持久化到缓存

    上游返回429时会将该episode加入冷却期并抛出 httpx.HTTPStatusError
    """
    from ..database import AsyncSessionLocal
    from ..models.danmaku import DanmakuCache

    path = f"/api/v2/comment/{episode_id}"
    signature, timestamp, app_id = generate_signature(path)

    headers = {
        'X-AppId': app_id,
        'X-Timestamp': timestamp,
        'X-Signature': signature
    }

    params = {
        'from': from_id,
        'withRelated': str(with_related).lower(),
        'chConvert': ch_convert
    }

    try:
        response = await throttled_request(
            "GET",
            f"{settings.DANDAN_API_BASE_URL}{path}",
            params=params,
            headers=headers,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            set_cooldown(f"{DANMAKU_COOLDOWN_PREFIX}{episode_id}")
            logger.warning(f"上游限流(429)，episode {episode_id} 进入{settings.FAILURE_COOLDOWN_MINUTES}分钟冷却期")
        raise

    data = response.json()

    # 写缓存失败不影响返回数据
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(DanmakuCache).where(DanmakuCache.episode_id == episode_id)
            result = await session.execute(stmt)
            existing_cache = result.scalar_one_or_none()

            if existing_cache:
                existing_cache.data = data
                existing_cache.updated_at = datetime.now()
                logger.info(f"更新弹幕数据缓存: episode_id={episode_id}")
            else:
                # 显式设置updated_at：模型只有onupdate没有insert默认值，
                # 否则新行的updated_at为NULL会被立刻判为过期
                session.add(DanmakuCache(
                    episode_id=episode_id,
                    data=data,
                    updated_at=datetime.now()
                ))
                logger.info(f"创建弹幕数据缓存: episode_id={episode_id}")

            await session.commit()
    except Exception as e:
        logger.error(f"保存弹幕数据到缓存时出错: {e}")

    return data


# ---------------------------------------------------------------------------
# 后台刷新队列：stale-while-revalidate的刷新端，按固定速率匀速消化
# ---------------------------------------------------------------------------
_refresh_queue: asyncio.Queue = asyncio.Queue(maxsize=settings.REFRESH_QUEUE_MAX)
_refresh_pending: Set[int] = set()
_worker_task: Optional[asyncio.Task] = None


def enqueue_refresh(episode_id: int) -> bool:
    """安排一次后台缓存刷新，重复/冷却中/队列满时丢弃并返回False"""
    if episode_id in _refresh_pending:
        return False
    if cooldown_remaining(f"{DANMAKU_COOLDOWN_PREFIX}{episode_id}") > 0:
        return False
    try:
        _refresh_queue.put_nowait(episode_id)
    except asyncio.QueueFull:
        logger.warning(f"后台刷新队列已满，丢弃 episode {episode_id}")
        return False
    _refresh_pending.add(episode_id)
    return True


async def _refresh_worker() -> None:
    """后台刷新任务：逐个回源过期缓存，每次之间强制间隔"""
    logger.info("弹幕缓存后台刷新任务已启动")
    while True:
        episode_id = await _refresh_queue.get()
        try:
            # 配额熔断期间暂停刷新，等熔断结束再处理当前条目
            quota_wait = quota_cooldown_remaining(QUOTA_GROUP_COMMENT)
            if quota_wait > 0:
                await asyncio.sleep(quota_wait)
            if cooldown_remaining(f"{DANMAKU_COOLDOWN_PREFIX}{episode_id}") > 0:
                continue
            await single_flight(
                f"{DANMAKU_COOLDOWN_PREFIX}{episode_id}",
                lambda: fetch_and_cache_danmaku(episode_id),
            )
            inc_metric("refresh_done")
            logger.info(f"后台刷新弹幕缓存完成: episode_id={episode_id}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            inc_metric("refresh_fail")
            logger.warning(f"后台刷新弹幕缓存失败: episode_id={episode_id}: {e}")
        finally:
            _refresh_pending.discard(episode_id)
            _refresh_queue.task_done()
        await asyncio.sleep(settings.REFRESH_INTERVAL_SECONDS)


def start_refresh_worker() -> None:
    """启动后台刷新任务（应用启动时调用）"""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_refresh_worker())


async def stop_refresh_worker() -> None:
    """停止后台刷新任务（应用关闭时调用）"""
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
