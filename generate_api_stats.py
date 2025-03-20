import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func, and_
from app.models.api_stats import ApiStats
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

async def generate_api_stats():
    # 创建数据库引擎
    engine = create_async_engine(
        "sqlite+aiosqlite:///./dandan.db",
        echo=True
    )
    
    # 创建会话工厂
    async_session = async_sessionmaker(
        engine,
        expire_on_commit=False
    )
    
    # 创建会话
    async with async_session() as session:
        try:
            # 获取最近24小时的数据
            start_time = datetime.now() - timedelta(hours=24)
            
            # 按端点统计调用次数
            endpoint_stats = await session.execute(
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
            hourly_stats = await session.execute(
                select(
                    func.strftime('%Y-%m-%d %H:00:00', ApiStats.timestamp).label('hour'),
                    func.count().label('count')
                )
                .where(ApiStats.timestamp >= start_time)
                .group_by('hour')
                .order_by('hour')
            )
            hourly_stats = hourly_stats.all()
            
            # 创建图表目录
            os.makedirs('stats', exist_ok=True)
            
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
            fig_endpoints.write_html('stats/endpoint_stats.html')
            
            # 生成时间趋势图表
            df_hourly = pd.DataFrame(hourly_stats, columns=['hour', 'count'])
            fig_hourly = px.line(df_hourly, x='hour', y='count',
                               title='24小时API调用趋势')
            fig_hourly.write_html('stats/hourly_stats.html')
            
            # 生成状态码分布图表
            status_stats = await session.execute(
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
            fig_status.write_html('stats/status_stats.html')
            
            print("统计图表已生成在 stats 目录下：")
            print("1. endpoint_stats.html - API端点统计")
            print("2. hourly_stats.html - 24小时调用趋势")
            print("3. status_stats.html - 状态码分布")
            
        except Exception as e:
            print(f"生成统计图表时发生错误: {e}")
        finally:
            await session.close()
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(generate_api_stats()) 