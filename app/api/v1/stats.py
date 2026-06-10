import hmac
import os
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.danmaku import DanmakuCache, TmdbCache
from app.models.file_match import FileMatch, MatchFailureCache
from app.services import upstream

router = APIRouter()

# 项目根目录下的templates
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DASHBOARD_HTML = os.path.join(BASE_DIR, "templates", "dashboard.html")


def verify_token(token: str = Query("")) -> None:
    """校验监控面板访问token，未配置token时面板不可用"""
    expected = settings.DASHBOARD_TOKEN
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="无效的访问token")


@router.get("/stats", response_class=HTMLResponse)
async def dashboard_page(_: None = Depends(verify_token)) -> HTMLResponse:
    """监控面板页面"""
    with open(DASHBOARD_HTML, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/stats/data")
async def dashboard_data(
    _: None = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """监控面板聚合数据（24小时窗口 + 进程内运行时指标）"""
    # api_stats的timestamp以UTC naive格式存储
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now_utc - timedelta(hours=24)
    hour_ago = now_utc - timedelta(hours=1)

    # 总览
    overview_row = (await db.execute(text("""
        SELECT COUNT(*),
               COALESCE(AVG(response_time), 0),
               COALESCE(SUM(CASE WHEN status_code BETWEEN 400 AND 499 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END), 0)
        FROM api_stats WHERE timestamp >= :cutoff
    """), {"cutoff": cutoff})).one()

    last_hour_count = (await db.execute(text(
        "SELECT COUNT(*) FROM api_stats WHERE timestamp >= :hour_ago"
    ), {"hour_ago": hour_ago})).scalar()

    # 按小时×状态码分类的趋势
    hourly_rows = (await db.execute(text("""
        SELECT strftime('%Y-%m-%dT%H:00:00Z', timestamp) AS hour,
               status_code / 100 AS cls,
               COUNT(*) AS cnt,
               AVG(response_time) AS avg_ms
        FROM api_stats WHERE timestamp >= :cutoff
        GROUP BY hour, cls ORDER BY hour
    """), {"cutoff": cutoff})).all()

    hourly: dict = {}
    for hour, cls, cnt, avg_ms in hourly_rows:
        bucket = hourly.setdefault(hour, {
            "hour": hour, "s2xx": 0, "s3xx": 0, "s4xx": 0, "s5xx": 0, "_t": 0.0, "_w": 0
        })
        key = f"s{cls}xx"
        if key in bucket:
            bucket[key] += cnt
        bucket["_t"] += (avg_ms or 0) * cnt
        bucket["_w"] += cnt
    hourly_list = []
    for b in hourly.values():
        b["avg_ms"] = round(b.pop("_t") / b["_w"]) if b["_w"] else 0
        del b["_w"]
        hourly_list.append(b)

    # 按端点类别统计
    category_rows = (await db.execute(text("""
        SELECT CASE
                 WHEN endpoint GLOB '/api/v1/[0-9]*' THEN '弹幕获取'
                 WHEN endpoint = '/api/v1/match' THEN '文件匹配'
                 WHEN endpoint = '/api/v1/match_with_danmaku' THEN '匹配+弹幕'
                 WHEN endpoint = '/api/v1/search/tmdb' THEN 'TMDB搜索'
                 WHEN endpoint = '/api/v1/search/anime' THEN '作品搜索'
                 ELSE '其他/扫描' END AS cat,
               COUNT(*) AS cnt,
               AVG(response_time) AS avg_ms,
               SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors
        FROM api_stats WHERE timestamp >= :cutoff
        GROUP BY cat ORDER BY cnt DESC
    """), {"cutoff": cutoff})).all()

    # 最近5xx错误
    error_rows = (await db.execute(text("""
        SELECT strftime('%Y-%m-%dT%H:%M:%SZ', timestamp), endpoint, status_code
        FROM api_stats
        WHERE timestamp >= :cutoff AND status_code >= 500
        ORDER BY id DESC LIMIT 10
    """), {"cutoff": cutoff})).all()

    # 缓存规模
    caches = {
        "danmaku": (await db.execute(select(func.count()).select_from(DanmakuCache))).scalar(),
        "file_match": (await db.execute(select(func.count()).select_from(FileMatch))).scalar(),
        "match_negative": (await db.execute(select(func.count()).select_from(MatchFailureCache))).scalar(),
        "tmdb": (await db.execute(select(func.count()).select_from(TmdbCache))).scalar(),
    }

    total, avg_ms, e4xx, e5xx = overview_row
    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "overview": {
            "total_24h": total,
            "last_hour": last_hour_count,
            "avg_ms": round(avg_ms),
            "errors_4xx": e4xx,
            "errors_5xx": e5xx,
        },
        "hourly": hourly_list,
        "categories": [
            {"name": c, "count": n, "avg_ms": round(a or 0), "errors": e}
            for c, n, a, e in category_rows
        ],
        "recent_errors": [
            {"time": t, "endpoint": ep, "status": s} for t, ep, s in error_rows
        ],
        "caches": caches,
        "upstream": upstream.runtime_status(),
    }
