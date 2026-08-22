import hmac
import json
import os
import re
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.danmaku import DanmakuCache, TmdbCache, TmdbSeriesNegative
from app.models.file_match import FileMatch, MatchFailureCache
from app.services import ip_budget, upstream

router = APIRouter()

# 项目根目录下的templates
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DASHBOARD_HTML = os.path.join(BASE_DIR, "templates", "dashboard.html")


# 弹幕获取请求的路径形如 /api/v1/{episodeId}
DANMAKU_PATH_RE = re.compile(r"^/api/v1/(\d+)$")

# 用于从文件名中提取作品名
FILE_EXT_RE = re.compile(r"\.[A-Za-z0-9]{2,5}$")
BRACKET_PREFIX_RE = re.compile(r"^(\[[^\]]*\]\s*)+")
EPISODE_MARKER_RE = re.compile(
    r"\s*-?\s*(S\d{1,2}E\d{1,4}|第\s*\d{1,4}\s*[话話集]|\bEP?\.?\s*\d{1,4}\b)"
    r"|\s-\s\d{1,4}(?=[\s\[\(]|$)",
    re.IGNORECASE,
)


def _anime_title_from_filename(file_name: str) -> str:
    """从匹配记录的文件名里尽量截出作品名（去掉扩展名、字幕组前缀和集数标记）"""
    name = FILE_EXT_RE.sub("", file_name)
    name = BRACKET_PREFIX_RE.sub("", name)
    m = EPISODE_MARKER_RE.search(name)
    if m and m.start() > 0:
        name = name[:m.start()]
    return name.strip(" -_·.") or file_name


async def _resolve_recent_requests(db: AsyncSession, limit: int = 50) -> list:
    """取最近请求并尽量反查出对应的作品/文件名"""
    rows = (await db.execute(text("""
        SELECT strftime('%Y-%m-%dT%H:%M:%SZ', timestamp), endpoint, method,
               status_code, response_time, params
        FROM api_stats ORDER BY id DESC LIMIT :limit
    """), {"limit": limit})).all()

    # 第一遍：解析类别，收集待反查的episodeId / tmdbId
    episode_ids: set = set()
    tmdb_ids: set = set()
    parsed = []
    for ts, endpoint, method, status, ms, params_raw in rows:
        try:
            params = json.loads(params_raw) if params_raw else None
        except Exception:
            params = None
        params = params if isinstance(params, dict) else {}

        eid = None
        m = DANMAKU_PATH_RE.match(endpoint)
        if m:
            cat = "弹幕获取"
            eid = int(m.group(1))
            episode_ids.add(eid)
        elif endpoint == "/api/v1/match":
            cat = "文件匹配"
        elif endpoint == "/api/v1/match_with_danmaku":
            cat = "匹配+弹幕"
        elif endpoint == "/api/v1/search/tmdb":
            cat = "TMDB搜索"
            if isinstance(params.get("tmdb_id"), int):
                tmdb_ids.add(params["tmdb_id"])
        elif endpoint == "/api/v1/search/anime":
            cat = "作品搜索"
        else:
            cat = "其他/扫描"
        parsed.append((ts, endpoint, method, status, ms, params, cat, eid))

    # 反查episodeId -> 文件名（精确命中），未命中的退而求同作品的任意文件
    exact: dict = {}
    sibling: dict = {}
    if episode_ids:
        ids_sql = ",".join(str(i) for i in episode_ids)
        exact = dict((await db.execute(text(f"""
            SELECT episode_id, MAX(file_name) FROM file_matches
            WHERE episode_id IN ({ids_sql}) GROUP BY episode_id
        """))).all())
        missing_aids = {i // 10000 for i in episode_ids if i not in exact}
        if missing_aids:
            aids_sql = ",".join(str(a) for a in missing_aids)
            sibling = dict((await db.execute(text(f"""
                SELECT episode_id / 10000 AS aid, MAX(file_name) FROM file_matches
                WHERE episode_id / 10000 IN ({aids_sql}) GROUP BY aid
            """))).all())

    # 仍未命中的作品再从TMDB搜索缓存反查标题（走ix_tmdb_anime_id表达式索引）
    tmdb_anime: dict = {}
    still_missing = {
        i // 10000 for i in episode_ids
        if i not in exact and i // 10000 not in sibling
    }
    if still_missing:
        aids_sql = ",".join(str(a) for a in still_missing)
        tmdb_anime = {
            k: v for k, v in (await db.execute(text(f"""
                SELECT json_extract(data, '$.animes[0].animeId') AS aid,
                       MAX(json_extract(data, '$.animes[0].animeTitle'))
                FROM tmdb_cache
                WHERE json_extract(data, '$.animes[0].animeId') IN ({aids_sql})
                GROUP BY aid
            """))).all() if v
        }

    # 反查tmdbId -> 作品标题（缓存的搜索结果里带animeTitle）；
    # 有缓存但animes为空说明弹弹play未收录该作品
    tmdb_titles: dict = {}
    tmdb_cached_empty: set = set()
    if tmdb_ids:
        tids_sql = ",".join(str(i) for i in tmdb_ids)
        for tid, title in (await db.execute(text(f"""
            SELECT tmdb_id, MAX(json_extract(data, '$.animes[0].animeTitle'))
            FROM tmdb_cache WHERE tmdb_id IN ({tids_sql}) GROUP BY tmdb_id
        """))).all():
            if title:
                tmdb_titles[tid] = title
            else:
                tmdb_cached_empty.add(tid)

    # 第二遍：拼装展示文本
    result = []
    for ts, endpoint, method, status, ms, params, cat, eid in parsed:
        url = None
        if cat == "弹幕获取":
            if eid in exact:
                detail = exact[eid]
            elif eid // 10000 in sibling:
                title = _anime_title_from_filename(sibling[eid // 10000])
                detail = f"《{title}》第{eid % 10000}话（作品名取自匹配记录）"
            elif eid // 10000 in tmdb_anime:
                detail = f"《{tmdb_anime[eid // 10000]}》第{eid % 10000}话（作品名取自TMDB缓存）"
            else:
                detail = f"episodeId {eid}"
        elif cat in ("文件匹配", "匹配+弹幕"):
            detail = params.get("file_name") or "—"
        elif cat == "TMDB搜索":
            tid, ep = params.get("tmdb_id"), params.get("episode")
            is_movie = params.get("tmdb_id_type") == 1
            ep_part = "（电影）" if is_movie else (f" 第{ep}话" if ep else "")
            title = tmdb_titles.get(tid)
            if title:
                detail = f"{title}{ep_part}" if is_movie else (f"{title}（第{ep}话）" if ep else title)
            elif tid:
                note = "（弹弹play未收录）" if tid in tmdb_cached_empty else ""
                detail = f"tmdbId {tid}{ep_part}{note}"
                url = f"https://www.themoviedb.org/{'movie' if is_movie else 'tv'}/{tid}"
            else:
                detail = "—"
        elif cat == "作品搜索":
            detail = params.get("keyword") or "—"
        else:
            detail = endpoint
        result.append({
            "time": ts, "method": method, "category": cat,
            "detail": detail, "status": status, "ms": ms, "url": url,
        })
    return result


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
        "tmdb_series_negative": (await db.execute(select(func.count()).select_from(TmdbSeriesNegative))).scalar(),
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
        "recent_requests": await _resolve_recent_requests(db),
        "caches": caches,
        "upstream": upstream.runtime_status(),
        "ip_budget": ip_budget.snapshot(),
    }
