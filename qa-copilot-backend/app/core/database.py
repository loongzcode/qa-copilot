# 配置数据库连接池，配置获取公共数据库连接和关闭连接
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 SQLAlchemy ORM 模型的基类。

    业务模型通过继承 ``Base`` 注册自己的表结构，例如 ``class User(Base)``。
    ``Base.metadata`` 会汇总这些模型的表信息，供 ``create_tables()`` 建表使用。
    """


# 创建数据库连接池
engine = create_async_engine(
    # 获取数据库连接地址
    settings.database_url,
    # 开发环境开启后，把生成的 SQL 和绑定参数打印到控制台，方便调试。
    echo=settings.debug,
    # 从连接池取连接前先检查连接是否有效，避免使用已经断开的连接
    pool_pre_ping=True,
)

# 创建 AsyncSession 工厂；这行代码本身不会创建某次请求使用的 Session。
# 调用 ``AsyncSessionLocal()`` 时，才会得到一个新的 AsyncSession。
#
# engine：该工厂创建的 Session 都绑定到上面的数据库引擎。
# class_=AsyncSession：创建支持 await 的异步 Session。
# expire_on_commit=False：commit 后 ORM 对象属性不立即过期，仍可直接读取。

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)  # noqa: E501


async def get_db() -> AsyncGenerator[AsyncSession]:
    """为一次 FastAPI 请求提供一个数据库 Session。

    FastAPI 通过 ``Depends(get_db)`` 调用这个异步生成器。``yield`` 前负责创建
    Session；``yield session`` 把同一个 Session 注入本次请求所需的依赖；
    请求结束后退出 ``async with``，关闭 Session，并把连接归还连接池。

    这里不会自动提交事务。新增、修改或删除成功后，Service/Repository 仍需
    显式调用 ``commit()``。如果业务代码抛出异常，则回滚尚未提交的事务，
    然后继续抛出原异常，让 FastAPI 的异常处理器生成响应。
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

