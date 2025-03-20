import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.models.base import Base
from app.models.file_match import FileMatch

async def check_database():
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
        # 查询所有记录
        stmt = select(FileMatch)
        result = await session.execute(stmt)
        matches = result.scalars().all()
        
        if not matches:
            print("数据库中没有任何记录")
            return
            
        print(f"找到 {len(matches)} 条记录：")
        print("-" * 50)
        
        for match in matches:
            print(f"ID: {match.id}")
            print(f"文件名: {match.file_name}")
            print(f"文件哈希: {match.file_hash}")
            print(f"文件大小: {match.file_size / (1024*1024):.2f} MB")
            print(f"视频时长: {match.video_duration} 秒")
            print(f"Episode ID: {match.episode_id}")
            print(f"创建时间: {match.created_at}")
            print(f"更新时间: {match.updated_at}")
            print("-" * 50)

if __name__ == "__main__":
    asyncio.run(check_database()) 