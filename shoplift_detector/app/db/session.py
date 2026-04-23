import logging
from typing import Annotated

from app.core.config import settings
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

# 1. Engine-д зориулсан үндсэн тохиргоонууд
engine_kwargs = {
    "pool_pre_ping": True,
    "echo": settings.DEBUG,
}

# 2. Зөвхөн Postgres/MySQL үед pooling тохиргоог нэмнэ
# SQLite 'pool_size' болон 'max_overflow'-г дэмждэггүй тул алдаа заадаг.
if "sqlite" not in settings.async_database_url.lower():
    engine_kwargs.update({
        "pool_size": 20,
        "max_overflow": 10,
        "pool_recycle": 300,
    })
else:
    # SQLite ашиглаж байгаа үед илүү тогтвортой байлгахын тулд StaticPool ашиглаж болно
    from sqlalchemy.pool import StaticPool
    engine_kwargs["poolclass"] = StaticPool

engine = create_async_engine(
    settings.async_database_url,
    **engine_kwargs
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# T02-25: Install the tenancy `after_begin` event listener once the
# sessionmaker is built. The handler reads ContextVars populated by
# `app.core.tenancy_context` and issues `SET LOCAL app.current_org_id`
# + `SET LOCAL app.bypass_tenant` against Postgres connections. SQLite
# is a no-op. Kept as a module-level side-effect so every code path
# that uses the app's DB session inherits the hook.
from app.db.tenancy_events import install_tenancy_event_hook  # noqa: E402

install_tenancy_event_hook()

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


DB = Annotated[AsyncSession, Depends(get_db)]
