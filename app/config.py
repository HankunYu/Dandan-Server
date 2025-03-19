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
    CACHE_EXPIRE_MINUTES: int = 60  # 缓存过期时间（分钟）
    
    class Config:
        env_file = ".env"

settings = Settings() 