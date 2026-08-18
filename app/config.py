from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # 数据库配置
    DATABASE_URL: str = "sqlite+aiosqlite:///./dandan.db"
    
    # 弹弹play API配置
    DANDAN_API_BASE_URL: str = "https://api.dandanplay.net"
    DANDAN_APP_ID: str
    DANDAN_APP_SECRET: str
    
    # 缓存配置
    CACHE_EXPIRE_MINUTES: int = 360
    # 缓存过期时间随机抖动范围（分钟），避免同一批缓存在同一时刻集体过期
    CACHE_TTL_JITTER_MINUTES: int = 90

    # 上游节流配置
    UPSTREAM_MAX_CONCURRENCY: int = 4
    UPSTREAM_MIN_INTERVAL_MS: int = 200
    # 上游429后该episode的冷却时间（分钟），冷却期内不再回源
    FAILURE_COOLDOWN_MINUTES: int = 10
    # 未匹配文件负缓存有效期（天），期内同一文件不再回源查询match
    MATCH_NEGATIVE_CACHE_DAYS: int = 1
    # TMDB搜索空结果的缓存有效期（天），过期后重新回源以便查到后续被弹弹play收录的作品；有结果的条目永久缓存
    TMDB_EMPTY_RESULT_TTL_DAYS: int = 7
    # 上游返回"配额上限"后的全局熔断时间（分钟），期间所有未命中缓存的请求不再回源
    QUOTA_COOLDOWN_MINUTES: int = 10

    # 后台缓存刷新配置
    REFRESH_INTERVAL_SECONDS: float = 0.5
    REFRESH_QUEUE_MAX: int = 2000

    # 监控面板访问token，为空则禁用面板
    DASHBOARD_TOKEN: str = ""

    # api_stats retention in days; older rows are purged daily. 0 = keep forever
    API_STATS_RETENTION_DAYS: int = 7

    class Config:
        env_file = ".env"

settings = Settings() 