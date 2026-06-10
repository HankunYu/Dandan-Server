from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.database import AsyncSessionLocal
from app.models.api_stats import ApiStats
import logging
import time
import json
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

# 不记录统计的路径前缀（监控面板自身的轮询不计入业务统计）
EXCLUDED_PREFIXES = ("/api/v1/stats",)


class ApiStatsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(EXCLUDED_PREFIXES):
            return await call_next(request)

        start_time = time.time()
        error_message = None

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            error_message = str(e)[:500]
            raise
        finally:
            # 统计写入失败绝不影响正常请求
            try:
                response_time = int((time.time() - start_time) * 1000)

                params = None
                if request.method in ("POST", "PUT"):
                    try:
                        body = await request.body()
                        if body:
                            params = json.loads(body)
                    except Exception:
                        pass
                else:
                    params = dict(request.query_params)

                async with AsyncSessionLocal() as session:
                    session.add(ApiStats(
                        endpoint=request.url.path,
                        method=request.method,
                        status_code=status_code,
                        response_time=response_time,
                        params=params,
                        error=error_message,
                        timestamp=datetime.now(UTC)
                    ))
                    await session.commit()
            except Exception as e:
                logger.warning(f"记录API统计失败: {e}")

        return response
