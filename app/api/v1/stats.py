from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.api_stats import ApiStats
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
import os

router = APIRouter()

# 获取当前文件所在目录的上级目录（项目根目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/stats", response_class=HTMLResponse)
async def get_stats(request: Request, db: AsyncSession = Depends(get_db)):
    """获取API统计图表"""
    try:
        # 获取最近24小时的数据
        start_time = datetime.now() - timedelta(hours=24)
        
        # 按端点统计调用次数
        endpoint_stats = await db.execute(
            select(
                ApiStats.endpoint,
                func.count().label('count'),
                func.avg(ApiStats.response_time).label('avg_response_time')
            )
            .where(ApiStats.timestamp >= start_time)
            .group_by(ApiStats.endpoint)
        )
        endpoint_stats = endpoint_stats.all()
        
        # 按小时统计调用次数
        hourly_stats = await db.execute(
            select(
                func.strftime('%Y-%m-%d %H:00:00', ApiStats.timestamp).label('hour'),
                func.count().label('count')
            )
            .where(ApiStats.timestamp >= start_time)
            .group_by('hour')
            .order_by('hour')
        )
        hourly_stats = hourly_stats.all()
        
        # 生成端点统计图表
        df_endpoints = pd.DataFrame(endpoint_stats, columns=['endpoint', 'count', 'avg_response_time'])
        fig_endpoints = make_subplots(rows=2, cols=1, 
                                   subplot_titles=('API调用次数', '平均响应时间'))
        
        fig_endpoints.add_trace(
            go.Bar(x=df_endpoints['endpoint'], y=df_endpoints['count'], name='调用次数'),
            row=1, col=1
        )
        
        fig_endpoints.add_trace(
            go.Bar(x=df_endpoints['endpoint'], y=df_endpoints['avg_response_time'], name='平均响应时间(ms)'),
            row=2, col=1
        )
        
        fig_endpoints.update_layout(height=800, title_text="API端点统计")
        endpoint_chart = fig_endpoints.to_html(full_html=False)
        
        # 生成时间趋势图表
        df_hourly = pd.DataFrame(hourly_stats, columns=['hour', 'count'])
        fig_hourly = px.line(df_hourly, x='hour', y='count',
                           title='24小时API调用趋势')
        hourly_chart = fig_hourly.to_html(full_html=False)
        
        # 生成状态码分布图表
        status_stats = await db.execute(
            select(
                ApiStats.status_code,
                func.count().label('count')
            )
            .where(ApiStats.timestamp >= start_time)
            .group_by(ApiStats.status_code)
        )
        status_stats = status_stats.all()
        
        df_status = pd.DataFrame(status_stats, columns=['status_code', 'count'])
        fig_status = px.pie(df_status, values='count', names='status_code',
                          title='API响应状态码分布')
        status_chart = fig_status.to_html(full_html=False)
        
        # 获取一些基本统计信息
        total_requests = await db.scalar(
            select(func.count()).select_from(ApiStats)
            .where(ApiStats.timestamp >= start_time)
        )
        
        avg_response_time = await db.scalar(
            select(func.avg(ApiStats.response_time)).select_from(ApiStats)
            .where(ApiStats.timestamp >= start_time)
        )
        
        error_count = await db.scalar(
            select(func.count()).select_from(ApiStats)
            .where(ApiStats.timestamp >= start_time, ApiStats.status_code >= 400)
        )
        
        return templates.TemplateResponse(
            "stats.html",
            {
                "request": request,
                "endpoint_chart": endpoint_chart,
                "hourly_chart": hourly_chart,
                "status_chart": status_chart,
                "total_requests": total_requests or 0,
                "avg_response_time": round(avg_response_time or 0, 2),
                "error_count": error_count or 0,
                "error_rate": round((error_count or 0) / (total_requests or 1) * 100, 2)
            }
        )
        
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": str(e)
            }
        ) 