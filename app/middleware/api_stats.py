from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.models.api_stats import ApiStats
import time
import json
from datetime import datetime, UTC

class ApiStatsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # 计算响应时间
            response_time = int((time.time() - start_time) * 1000)
            
            # 获取请求参数
            params = None
            if request.method in ["POST", "PUT"]:
                try:
                    body = await request.body()
                    if body:
                        params = json.loads(body)
                except:
                    pass
            else:
                params = dict(request.query_params)
            
            # 记录API调用
            async with AsyncSessionLocal() as session:
                stats = ApiStats(
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    response_time=response_time,
                    params=params,
                    timestamp=datetime.now(UTC)
                )
                session.add(stats)
                await session.commit()
            
            return response
            
        except Exception as e:
            # 记录错误信息
            async with AsyncSessionLocal() as session:
                stats = ApiStats(
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=500,
                    response_time=int((time.time() - start_time) * 1000),
                    params=dict(request.query_params),
                    error=str(e),
                    timestamp=datetime.now(UTC)
                )
                session.add(stats)
                await session.commit()
            raise 