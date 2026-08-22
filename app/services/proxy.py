import httpx
import logging
from typing import Dict, Any, Optional, List
from ..config import settings
from .signature import generate_signature
from . import ip_budget, upstream
from fastapi import HTTPException
from app.models.danmaku import MatchResponse, DanmakuCache, TmdbCache, TmdbSeriesNegative
from app.models.file_match import FileMatch, MatchFailureCache
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timedelta

# 配置日志记录器
logger = logging.getLogger(__name__)

# 上游"无结果"响应的标准形状，系列级负缓存命中时直接返回
EMPTY_SEARCH_RESULT = {
    "hasMore": False,
    "animes": [],
    "errorCode": 0,
    "success": True,
    "errorMessage": ""
}


def jittered_ttl(episode_id: int) -> timedelta:
    """默认TTL加上按episode确定性的随机抖动

    同一波写入的缓存如果都用固定TTL，会在24小时后的同一时刻集体过期，
    与客户端的定时重试洪峰精确对齐。抖动把过期时间摊开。
    """
    base = settings.CACHE_EXPIRE_MINUTES
    # 抖动不超过基础TTL的1/4，避免小TTL时有效期变负
    jitter_range = min(settings.CACHE_TTL_JITTER_MINUTES, base // 4)
    if jitter_range <= 0:
        return timedelta(minutes=base)
    # Knuth multiplicative hash keeps the jitter stable per episode
    jitter = (episode_id * 2654435761) % (2 * jitter_range + 1) - jitter_range
    return timedelta(minutes=base + jitter)


class DanmakuProxy:
    def __init__(self, db: AsyncSession, client_ip: Optional[str] = None):
        self.base_url = settings.DANDAN_API_BASE_URL
        self.db = db
        self.client_ip = client_ip
        self.cache_ttl = timedelta(minutes=settings.CACHE_EXPIRE_MINUTES)

    def _consume_ip_budget(self) -> bool:
        """尝试为本次回源扣减该IP的每日预算，超额返回False"""
        if ip_budget.try_consume(self.client_ip):
            return True
        upstream.inc_metric("ip_budget_blocked")
        return False

    def _ip_budget_exceeded(self) -> HTTPException:
        return HTTPException(
            status_code=429,
            detail="已达到单IP每日回源限额，请明天再试",
            headers={"Retry-After": str(ip_budget.seconds_until_reset())}
        )

    async def get_danmaku(
        self,
        episode_id: int,
        from_id: int = 0,
        with_related: bool = True,
        ch_convert: int = 0,
        cache_ttl: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        从弹弹play获取弹幕数据，支持数据库缓存
        
        Args:
            episode_id: 节目编号
            from_id: 起始弹幕编号，忽略此编号以前的弹幕
            with_related: 是否同时获取关联的第三方弹幕
            ch_convert: 中文简繁转换。0-不转换，1-转换为简体，2-转换为繁体
            cache_ttl: 缓存过期时间（分钟），如果为None则使用默认配置
            
        Returns:
            Optional[Dict[str, Any]]: 弹幕数据
        """
        # 显式传入的cache_ttl优先，否则使用带抖动的默认TTL
        if cache_ttl is not None:
            ttl = timedelta(minutes=cache_ttl)
        else:
            ttl = jittered_ttl(episode_id)

        # 读取缓存（不论新旧）
        cached: Optional[DanmakuCache] = None
        try:
            stmt = select(DanmakuCache).where(DanmakuCache.episode_id == episode_id)
            result = await self.db.execute(stmt)
            cached = result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"从缓存获取弹幕数据时出错: {e}")

        if cached is not None:
            # 旧数据没有updated_at时回退到created_at判断新鲜度
            cached_at = cached.updated_at or cached.created_at
            if cached_at is not None and cached_at >= datetime.now() - ttl:
                upstream.inc_metric("danmaku_cache_hit")
                logger.info(f"从缓存获取弹幕数据: episode_id={episode_id}")
                return cached.data

            # Stale-while-revalidate：立即返回过期数据，后台匀速刷新
            upstream.inc_metric("danmaku_stale_served")
            if upstream.enqueue_refresh(episode_id):
                logger.info(f"返回过期缓存并安排后台刷新: episode_id={episode_id}")
            else:
                logger.info(f"返回过期缓存(已在刷新队列或冷却中): episode_id={episode_id}")
            return cached.data

        # 完全没有缓存，必须同步回源；冷却期/配额熔断期内直接拒绝，避免撞限流
        cooldown = max(
            upstream.cooldown_remaining(f"{upstream.DANMAKU_COOLDOWN_PREFIX}{episode_id}"),
            upstream.quota_cooldown_remaining(upstream.QUOTA_GROUP_COMMENT),
        )
        if cooldown > 0:
            upstream.inc_metric("danmaku_blocked")
            raise HTTPException(
                status_code=503,
                detail="上游接口限流冷却中，请稍后重试",
                headers={"Retry-After": str(max(1, int(cooldown)))}
            )

        if not self._consume_ip_budget():
            raise self._ip_budget_exceeded()

        try:
            # Single-flight合并相同episode的并发回源
            upstream.inc_metric("danmaku_cold_fetch")
            return await upstream.single_flight(
                f"{upstream.DANMAKU_COOLDOWN_PREFIX}{episode_id}",
                lambda: upstream.fetch_and_cache_danmaku(
                    episode_id=episode_id,
                    from_id=from_id,
                    with_related=with_related,
                    ch_convert=ch_convert,
                ),
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"获取弹幕数据时发生HTTP错误: {e}")
            if e.response.status_code == 429:
                raise HTTPException(
                    status_code=503,
                    detail="上游接口限流，请稍后重试",
                    headers={"Retry-After": str(settings.FAILURE_COOLDOWN_MINUTES * 60)}
                )
            raise HTTPException(status_code=500, detail=str(e))
        except httpx.HTTPError as e:
            logger.error(f"获取弹幕数据时发生HTTP错误: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取弹幕数据时发生意外错误: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def match_file(
        self,
        file_name: str,
        file_hash: str,
        file_size: int,
        video_duration: int,
        match_mode: str = "hashAndFileName"
    ) -> MatchResponse:
        """
        通过文件信息匹配节目
        
        Args:
            file_name: 文件名
            file_hash: 文件前16MB的MD5哈希值
            file_size: 文件大小（字节）
            video_duration: 视频时长（秒）
            match_mode: 匹配模式（hashAndFileName: 文件名和哈希值匹配）
            
        Returns:
            MatchResponse: 匹配结果
        """
        # 首先检查缓存中是否存在匹配记录
        try:
            stmt = select(FileMatch).where(FileMatch.file_hash == file_hash)
            result = await self.db.execute(stmt)
            existing_match = result.scalar_one_or_none()
            
            if existing_match:
                upstream.inc_metric("match_cache_hit")
                logger.info(f"从缓存获取文件匹配记录: {file_name}")
                return MatchResponse(
                    isMatched=True,
                    matches=[{
                        'episodeId': existing_match.episode_id,
                        'fileName': existing_match.file_name,
                        'fileSize': existing_match.file_size,
                        'videoDuration': existing_match.video_duration
                    }]
                )
        except Exception as e:
            logger.error(f"从缓存获取文件匹配记录时出错: {e}")

        # 检查负缓存：近期已确认无法匹配的文件直接返回，不再回源
        try:
            stmt = select(MatchFailureCache).where(MatchFailureCache.file_hash == file_hash)
            result = await self.db.execute(stmt)
            failure = result.scalar_one_or_none()
            if failure is not None and failure.updated_at is not None:
                ttl = timedelta(days=settings.MATCH_NEGATIVE_CACHE_DAYS)
                if failure.updated_at >= datetime.now() - ttl:
                    upstream.inc_metric("match_negative_hit")
                    logger.info(f"命中未匹配负缓存: {file_name}")
                    return MatchResponse(isMatched=False, matches=[])
        except Exception as e:
            logger.error(f"读取未匹配负缓存时出错: {e}")

        # 识别组配额熔断期间不再回源
        if upstream.quota_cooldown_remaining(upstream.QUOTA_GROUP_MATCH) > 0:
            return MatchResponse(
                errorCode=429,
                success=False,
                errorMessage="上游接口配额受限，请稍后重试",
                isMatched=False,
                matches=[]
            )

        if not self._consume_ip_budget():
            return MatchResponse(
                errorCode=429,
                success=False,
                errorMessage="已达到单IP每日回源限额，请明天再试",
                isMatched=False,
                matches=[]
            )

        # 如果缓存不存在，从API获取数据
        path = "/api/v2/match"
        signature, timestamp, app_id = generate_signature(path)
        
        data = {
            'fileName': file_name,
            'fileHash': file_hash,
            'fileSize': file_size,
            'videoDuration': video_duration,
            'matchMode': match_mode
        }
        
        headers = {
            'X-AppId': app_id,
            'X-Timestamp': timestamp,
            'X-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        try:
            upstream.inc_metric("match_upstream")
            response = await upstream.throttled_request(
                "POST",
                f"{self.base_url}{path}",
                json=data,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            
            if not isinstance(result, dict):
                raise ValueError("Invalid response format")

            # 上游返回"配额上限"时熔断识别组
            if result.get('errorCode') == 429:
                upstream.trip_quota_breaker(upstream.QUOTA_GROUP_MATCH)

            # 确保 matches 字段是列表类型
            if result.get('matches') is None:
                result['matches'] = []
            
            # 如果匹配成功，保存文件信息到数据库
            if result.get('isMatched') and result.get('matches'):
                match_item = result['matches'][0]  # 使用第一个匹配结果
                try:
                    # 检查是否已存在相同的hash
                    stmt = select(FileMatch).where(FileMatch.file_hash == file_hash)
                    existing = await self.db.execute(stmt)
                    existing_match = existing.scalar_one_or_none()

                    if not existing_match:
                        # 创建新的文件匹配记录
                        file_match = FileMatch(
                            file_hash=file_hash,
                            episode_id=match_item['episodeId'],
                            file_name=file_name,
                            file_size=file_size,
                            video_duration=video_duration
                        )
                        self.db.add(file_match)
                        await self.db.commit()
                        logger.info(f"成功保存文件匹配记录: {file_name}")
                except Exception as e:
                    logger.error(f"保存文件匹配记录时出错: {e}")
                    await self.db.rollback()
                # 匹配成功后清除可能存在的负缓存（官方库后来收录了该文件）
                await self._clear_match_failure(file_hash)
            elif result.get('success', True):
                # 上游明确返回"无匹配"（非上游错误）→ 写入负缓存，
                # 避免刮削插件每个扫描周期对同一批无法匹配的文件重复回源
                await self._save_match_failure(file_hash, file_name)

            return MatchResponse(**result)
            
        except Exception as e:
            logger.error(f"匹配文件时发生错误: {e}")
            return MatchResponse(
                errorCode=500,
                success=False,
                errorMessage=str(e),
                isMatched=False,
                matches=[]
            )

    async def _save_match_failure(self, file_hash: str, file_name: str) -> None:
        """记录或刷新一条未匹配负缓存"""
        try:
            stmt = select(MatchFailureCache).where(MatchFailureCache.file_hash == file_hash)
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.file_name = file_name
                existing.updated_at = datetime.now()
            else:
                self.db.add(MatchFailureCache(
                    file_hash=file_hash,
                    file_name=file_name,
                    updated_at=datetime.now()
                ))
            await self.db.commit()
            logger.info(f"记录未匹配负缓存: {file_name}")
        except Exception as e:
            logger.error(f"保存未匹配负缓存时出错: {e}")
            await self.db.rollback()

    async def _clear_match_failure(self, file_hash: str) -> None:
        """删除该文件的负缓存记录（如存在）"""
        try:
            stmt = delete(MatchFailureCache).where(MatchFailureCache.file_hash == file_hash)
            await self.db.execute(stmt)
            await self.db.commit()
        except Exception as e:
            logger.error(f"清除未匹配负缓存时出错: {e}")
            await self.db.rollback()

    async def get_danmaku_with_detail(
        self,
        file_name: str,
        file_hash: str,
        file_size: int,
        video_duration: int,
        match_mode: str = "hashAndFileName",
        from_id: int = 0,
        with_related: bool = True,
        ch_convert: int = 0,
        cache_ttl: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        通过文件信息匹配节目并获取弹幕数据
        
        Args:
            file_name: 文件名
            file_hash: 文件前16MB的MD5哈希值
            file_size: 文件大小（字节）
            video_duration: 视频时长（秒）
            match_mode: 匹配模式（hashAndFileName: 文件名和哈希值匹配）
            from_id: 起始弹幕编号，忽略此编号以前的弹幕
            with_related: 是否同时获取关联的第三方弹幕
            ch_convert: 中文简繁转换。0-不转换，1-转换为简体，2-转换为繁体
            cache_ttl: 缓存过期时间（分钟），如果为None则使用默认配置
            
        Returns:
            Optional[Dict[str, Any]]: 弹幕数据，如果匹配失败则返回 None
        """
        # 首先进行文件匹配
        match_result = await self.match_file(
            file_name=file_name,
            file_hash=file_hash,
            file_size=file_size,
            video_duration=video_duration,
            match_mode=match_mode
        )
        
        # 如果匹配成功，获取弹幕数据
        if match_result.isMatched and match_result.matches:
            episode_id = match_result.matches[0]['episodeId']
            return await self.get_danmaku(
                episode_id=episode_id,
                from_id=from_id,
                with_related=with_related,
                ch_convert=ch_convert,
                cache_ttl=cache_ttl
            )
        
        logger.warning(f"文件匹配失败: {file_name}")
        return None

    async def search_by_tmdb(self, tmdb_id: int, episode: int, tmdb_id_type: int = 0) -> Dict[str, Any]:
        """
        通过TMDB ID搜索动画剧集，支持缓存

        Args:
            tmdb_id: TMDB ID
            episode: 集数
            tmdb_id_type: tmdbId类型，0=电视剧（默认），1=电影

        Returns:
            Dict[str, Any]: 搜索结果
        """
        # 首先尝试从缓存获取数据。
        # 有结果的条目永久有效；空结果只在TTL内有效，过期后重新回源，
        # 以便查到后续才被弹弹play收录的作品（过期的空结果保留作回源失败时的兜底）
        stale_empty: Optional[Dict[str, Any]] = None
        try:
            stmt = select(TmdbCache).where(
                TmdbCache.tmdb_id == tmdb_id,
                TmdbCache.id_type == tmdb_id_type,
                TmdbCache.episode == episode
            )
            result = await self.db.execute(stmt)
            cached_data = result.scalar_one_or_none()

            if cached_data:
                data = cached_data.data
                is_empty = isinstance(data, dict) and not data.get('animes')
                cached_at = cached_data.updated_at or cached_data.created_at
                empty_expired = is_empty and (
                    cached_at is None or
                    datetime.now() - cached_at > timedelta(days=settings.TMDB_EMPTY_RESULT_TTL_DAYS)
                )
                if empty_expired:
                    stale_empty = data
                    logger.info(f"TMDB空结果缓存过期，重新回源: tmdb_id={tmdb_id}, type={tmdb_id_type}, episode={episode}")
                else:
                    upstream.inc_metric("tmdb_cache_hit")
                    logger.info(f"从缓存获取TMDB搜索结果: tmdb_id={tmdb_id}, type={tmdb_id_type}, episode={episode}")
                    return data
        except Exception as e:
            logger.error(f"从缓存获取TMDB搜索结果时出错: {e}")

        # 系列级负缓存：整部确认无结果的作品直接返回空，不再逐集回源
        if await self._series_negative_fresh(tmdb_id, tmdb_id_type):
            upstream.inc_metric("tmdb_series_negative_hit")
            logger.info(f"命中系列级负缓存: tmdb_id={tmdb_id}, type={tmdb_id_type}")
            return stale_empty if stale_empty is not None else dict(EMPTY_SEARCH_RESULT)

        # 搜索组配额熔断期间不再回源
        quota_wait = upstream.quota_cooldown_remaining(upstream.QUOTA_GROUP_SEARCH)
        if quota_wait > 0:
            if stale_empty is not None:
                return stale_empty
            raise HTTPException(
                status_code=503,
                detail="上游接口配额受限，请稍后重试",
                headers={"Retry-After": str(max(1, int(quota_wait)))}
            )

        if not self._consume_ip_budget():
            if stale_empty is not None:
                return stale_empty
            raise self._ip_budget_exceeded()

        # 如果缓存不存在，从API获取数据
        path = f"/api/v2/search/episodes"
        signature, timestamp, app_id = generate_signature(path)
        
        params = {
            'tmdbId': tmdb_id,
            'tmdbIdType': tmdb_id_type
        }
        # 电影没有集数概念，传数字episode会被上游按集数过滤导致空结果，仅TV类型传递
        if tmdb_id_type == 0:
            params['episode'] = episode

        headers = {
            'X-AppId': app_id,
            'X-Timestamp': timestamp,
            'X-Signature': signature
        }
        
        try:
            upstream.inc_metric("tmdb_upstream")
            response = await upstream.throttled_request(
                "GET",
                f"{self.base_url}{path}",
                params=params,
                headers=headers,
                follow_redirects=True
            )
            response.raise_for_status()
            data = response.json()

            # 上游返回错误响应（如配额上限）时不写缓存，避免永久污染缓存
            if isinstance(data, dict) and data.get('success') is False:
                if data.get('errorCode') == 429:
                    upstream.trip_quota_breaker(upstream.QUOTA_GROUP_SEARCH)
                logger.warning(
                    f"TMDB搜索上游返回错误，不缓存: tmdb_id={tmdb_id}, "
                    f"episode={episode}, errorCode={data.get('errorCode')}"
                )
                return stale_empty if stale_empty is not None else data

            # 保存到缓存
            try:
                # 检查是否已存在缓存
                stmt = select(TmdbCache).where(
                    TmdbCache.tmdb_id == tmdb_id,
                    TmdbCache.id_type == tmdb_id_type,
                    TmdbCache.episode == episode
                )
                result = await self.db.execute(stmt)
                existing_cache = result.scalar_one_or_none()

                if existing_cache:
                    # 更新现有缓存
                    existing_cache.data = data
                    existing_cache.updated_at = datetime.now()
                    logger.info(f"更新TMDB搜索结果缓存: tmdb_id={tmdb_id}, type={tmdb_id_type}, episode={episode}")
                else:
                    # 创建新缓存
                    cache = TmdbCache(
                        tmdb_id=tmdb_id,
                        id_type=tmdb_id_type,
                        episode=episode,
                        data=data
                    )
                    self.db.add(cache)
                    logger.info(f"创建TMDB搜索结果缓存: tmdb_id={tmdb_id}, type={tmdb_id_type}, episode={episode}")
                
                await self.db.commit()
            except Exception as e:
                logger.error(f"保存TMDB搜索结果到缓存时出错: {e}")
                await self.db.rollback()

            # 维护系列级负缓存：电影查询本就不带集数、结果即系列级定论；
            # 电视剧空结果可能只是该集缺失，需一次不带集数的探测来确认整部是否无结果
            is_empty = isinstance(data, dict) and not data.get('animes')
            if not is_empty:
                await self._clear_series_negative(tmdb_id, tmdb_id_type)
            elif tmdb_id_type == 1:
                await self._save_series_negative(tmdb_id, tmdb_id_type)
            else:
                await self._probe_series_negative(tmdb_id, tmdb_id_type)

            return data
        except httpx.HTTPError as e:
            logger.error(f"搜索动画时发生HTTP错误: {e}")
            if stale_empty is not None:
                return stale_empty
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"搜索动画时发生意外错误: {e}")
            if stale_empty is not None:
                return stale_empty
            raise HTTPException(status_code=500, detail=str(e))

    async def _series_negative_fresh(self, tmdb_id: int, id_type: int) -> bool:
        """该作品是否有未过期的系列级负缓存记录"""
        try:
            stmt = select(TmdbSeriesNegative).where(
                TmdbSeriesNegative.tmdb_id == tmdb_id,
                TmdbSeriesNegative.id_type == id_type
            )
            result = await self.db.execute(stmt)
            record = result.scalar_one_or_none()
            if record is not None and record.updated_at is not None:
                ttl = timedelta(days=settings.TMDB_EMPTY_RESULT_TTL_DAYS)
                return record.updated_at >= datetime.now() - ttl
        except Exception as e:
            logger.error(f"读取系列级负缓存时出错: {e}")
        return False

    async def _save_series_negative(self, tmdb_id: int, id_type: int) -> None:
        """记录或刷新一条系列级负缓存"""
        try:
            stmt = select(TmdbSeriesNegative).where(
                TmdbSeriesNegative.tmdb_id == tmdb_id,
                TmdbSeriesNegative.id_type == id_type
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.updated_at = datetime.now()
            else:
                self.db.add(TmdbSeriesNegative(
                    tmdb_id=tmdb_id,
                    id_type=id_type,
                    updated_at=datetime.now()
                ))
            await self.db.commit()
            logger.info(f"记录系列级负缓存: tmdb_id={tmdb_id}, type={id_type}")
        except Exception as e:
            logger.error(f"保存系列级负缓存时出错: {e}")
            await self.db.rollback()

    async def _clear_series_negative(self, tmdb_id: int, id_type: int) -> None:
        """删除该作品的系列级负缓存记录（如存在，作品后来被弹弹play收录）"""
        try:
            stmt = delete(TmdbSeriesNegative).where(
                TmdbSeriesNegative.tmdb_id == tmdb_id,
                TmdbSeriesNegative.id_type == id_type
            )
            await self.db.execute(stmt)
            await self.db.commit()
        except Exception as e:
            logger.error(f"清除系列级负缓存时出错: {e}")
            await self.db.rollback()

    async def _probe_series_negative(self, tmdb_id: int, id_type: int) -> None:
        """不带集数探测整部作品，确认无结果则写入系列级负缓存

        每部作品每个TTL周期只发生一次，把逐集空查询收敛为一次探测。
        探测失败只影响负缓存收敛速度，绝不影响主请求的返回。
        """
        if not ip_budget.try_consume(self.client_ip):
            return
        try:
            path = "/api/v2/search/episodes"
            signature, timestamp, app_id = generate_signature(path)
            headers = {
                'X-AppId': app_id,
                'X-Timestamp': timestamp,
                'X-Signature': signature
            }
            upstream.inc_metric("tmdb_upstream")
            response = await upstream.throttled_request(
                "GET",
                f"{self.base_url}{path}",
                params={'tmdbId': tmdb_id, 'tmdbIdType': id_type},
                headers=headers,
                follow_redirects=True
            )
            response.raise_for_status()
            probe = response.json()
            if not isinstance(probe, dict):
                return
            if probe.get('success') is False:
                if probe.get('errorCode') == 429:
                    upstream.trip_quota_breaker(upstream.QUOTA_GROUP_SEARCH)
                return
            if not probe.get('animes'):
                await self._save_series_negative(tmdb_id, id_type)
        except Exception as e:
            logger.warning(f"系列级探测失败: tmdb_id={tmdb_id}, type={id_type}: {e}")

    async def search_anime(self, keyword: str, anime_type: Optional[str] = None) -> Dict[str, Any]:
        """
        根据关键词搜索动画作品

        Args:
            keyword: 搜索关键词，至少两个字符
            anime_type: 限定的动画类型，可选

        Returns:
            Dict[str, Any]: 搜索结果
        """
        # 关键词搜索无缓存，每次都消耗上游配额，与tmdb搜索共用搜索组熔断与IP预算
        quota_wait = upstream.quota_cooldown_remaining(upstream.QUOTA_GROUP_SEARCH)
        if quota_wait > 0:
            raise HTTPException(
                status_code=503,
                detail="上游接口配额受限，请稍后重试",
                headers={"Retry-After": str(max(1, int(quota_wait)))}
            )

        if not self._consume_ip_budget():
            raise self._ip_budget_exceeded()

        path = "/api/v2/search/anime"
        signature, timestamp, app_id = generate_signature(path)

        params = {"keyword": keyword}
        if anime_type:
            params["type"] = anime_type

        headers = {
            "X-AppId": app_id,
            "X-Timestamp": timestamp,
            "X-Signature": signature
        }

        try:
            response = await upstream.throttled_request(
                "GET",
                f"{self.base_url}{path}",
                params=params,
                headers=headers,
                follow_redirects=True
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get('success') is False and data.get('errorCode') == 429:
                upstream.trip_quota_breaker(upstream.QUOTA_GROUP_SEARCH)
            return data
        except httpx.HTTPError as e:
            logger.error(f"搜索作品时发生HTTP错误: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"搜索作品时发生意外错误: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def close(self):
        """保留以兼容现有调用；共享HTTP客户端在应用关闭时统一关闭"""
        pass
