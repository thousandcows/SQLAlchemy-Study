# Table of Contents
[GitHub Wiki TOC generator](https://ecotrust-canada.github.io/markdown-toc/)

# Synopsis - Core

create_async_engine 함수는 기존 Engine API의 async 버전을 제공하는 AsyncEngine 인스턴스를 생성한다. AsyncEngine은 비동기 context manager를 제공하는 AsyncEngine.connect() 또는 AsyncEngine.begin() 메서드를 통해 AsyncConnection을 전달한다. 그 다음 AsyncConnection은 명령문을 실행할 수 있다. AsyncConnection.execute()를 실행해 버퍼된 Result를 전달하거나, AsyncConnection.stream()을 활용하여 스트리밍 서버 사이드 AsyncResult를 전달할 수 있다.

```
import asyncio

from sqlalchemy import Column
from sqlalchemy import MetaData
from sqlalchemy import select
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import create_async_engine

meta = MetaData()
t1 = Table("t1", meta, Column("name", String(50), primary_key=True))


async def async_main() -> None:
    engine = create_async_engine(
        "postgresql+asyncpg://scott:tiger@localhost/test",
        echo=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(meta.create_all)

        await conn.execute(
            t1.insert(), [{"name": "some name 1"}, {"name": "some name 2"}]
        )

    async with engine.connect() as conn:
        # select a Result, which will be delivered with buffered
        # results
        result = await conn.execute(select(t1).where(t1.c.name == "some name 1"))

        print(result.fetchall())

    # for AsyncEngine created in function scope, close and
    # clean-up pooled connections
    await engine.dispose()


asyncio.run(async_main())

```

AsyncConnection.run_sync() 메서드는 awaitable한 hook를 포함하지 않는 MetaData.create_all()과 같은 특수한 DDL 함수를 호출하는데 사용될 수 있다.

AsyncConnection은 또한 AsyncResult 객체를 리턴하는 AsyncConnection.stream() 메서드를 통해 "streaming" API를 제공한다. 이 API는 서버측 커서를 사용하고, 비동기 iterator와 같은 async/await API를 제공한다.

# Synopsis - ORM

AsyncSession은 2.0 스타일 쿼리를 사용하여 전체 ORM 기능을 제공한다. 기본 사용 모드에서, lazy loading 또는 기타 만료된 속성에 대한 접근을 피하기 위해 주의가 필요하다(ORM relationship, column attributes를 포함). 다음 섹션(Preventing Implicit IO when Using AsyncSession)에서 좀 더 깊게 다룰 예정이다.

```
from __future__ import annotations

import asyncio
import datetime
from typing import List

from sqlalchemy import ForeignKey
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import selectinload


class Base(DeclarativeBase):
    pass


class A(Base):
    __tablename__ = "a"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[str]
    create_date: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    bs: Mapped[List[B]] = relationship(lazy="raise")


class B(Base):
    __tablename__ = "b"
    id: Mapped[int] = mapped_column(primary_key=True)
    a_id: Mapped[int] = mapped_column(ForeignKey("a.id"))
    data: Mapped[str]


async def insert_objects(async_session: async_sessionmaker[AsyncSession]) -> None:

    async with async_session() as session:
        async with session.begin():
            session.add_all(
                [
                    A(bs=[B(), B()], data="a1"),
                    A(bs=[], data="a2"),
                    A(bs=[B(), B()], data="a3"),
                ]
            )


async def select_and_update_objects(
    async_session: async_sessionmaker[AsyncSession],
) -> None:

    async with async_session() as session:
        stmt = select(A).options(selectinload(A.bs))

        result = await session.execute(stmt)

        for a1 in result.scalars():
            print(a1)
            print(f"created at: {a1.create_date}")
            for b1 in a1.bs:
                print(b1)

        result = await session.execute(select(A).order_by(A.id).limit(1))

        a1 = result.scalars().one()

        a1.data = "new data"

        await session.commit()

        # access attribute subsequent to commit; this is what
        # expire_on_commit=False allows
        print(a1.data)


async def async_main() -> None:
    engine = create_async_engine(
        "postgresql+asyncpg://scott:tiger@localhost/test",
        echo=True,
    )

    # async_sessionmaker: a factory for new AsyncSession objects.
    # expire_on_commit - don't expire objects after transaction commit
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await insert_objects(async_session)
    await select_and_update_objects(async_session)

    # for AsyncEngine created in function scope, close and
    # clean-up pooled connections
    await engine.dispose()


asyncio.run(async_main())

```

위 예에서 AsyncSession은 async_sessionmaker 선택적인 도우미를 사용하여 인스턴스화된다. 이 때 async_sessionmaker는 고정된 파라미터 집합으로 설정된 AsyncEngine 팩토리를 제공한다. 여기서는 특정 데이터베이스 URL과 연결하는 것을 포함하고 있다. 그런 다음 Python 비동기 컨텍스트 매니저 내에서 실행될 수도 있는 다른 메서드에게 세션 인스턴스가 전달된다. 메서드는 블록 끝에서 자동으로 close되는데, AsyncSession.close() 메서드를 호출하는 것과 동일하다.

## Preventing Implicit IO when Using AsyncSession

```
stmt = select(A).options(selectinload(A.bs))
```

```
A(bs=[], data="a2")
```

```
# create AsyncSession with expire_on_commit=False
async_session = AsyncSession(engine, expire_on_commit=False)

# sessionmaker version
async_session = async_sessionmaker(engine, expire_on_commit=False)

async with async_session() as session:
    result = await session.execute(select(A).order_by(A.id))

    a1 = result.scalars().first()

    # commit would normally expire all attributes
    await session.commit()

    # access attribute subsequent to commit; this is what
    # expire_on_commit=False allows
    print(a1.data)
```

```
# assume a_obj is an A that has lazy loaded A.bs collection
a_obj = await async_session.get(A, [1])

# force the collection to load by naming it in attribute_names
await async_session.refresh(a_obj, ["bs"])

# collection is present
print(f"bs collection: {a_obj.bs}")
```

```
user = await session.get(User, 42)
addresses = (await session.scalars(user.addresses.statement)).all()
stmt = user.addresses.statement.where(Address.email_address.startswith("patrick"))
addresses_filter = (await session.scalars(stmt)).all()
```

## Running Synchronous Methods and Functions under asyncio

# Using events with the asyncio extension
## Examples of Event Listeners with Async Engines / Sessions / Sessionmakers

## Using awaitable-only driver methods in connection pool and other events

# Using multiple asyncio event loops

asyncio와 멀티쓰레딩을 결합한 경우처럼, 여러 개의 이벤트 루프를 사용하는 애플리케이션은 default pool을 사용할 때 이벤트 루프 간 같은 AsyncEngine을 공유해서는 안된다.

만약 AsyncEngine이 한 이벤트 루프에서 다른 이벤트 루프로 전달되는 경우, 엔진이 새 이벤트 루프에서 사용되기 전 AsyncEngine.dispose() 메서드를 호출하여야 한다. 이에 실패하는 경우 "Task <Task pending ...> got Future attached to a different loop"와 같은 RuntimeError가 발생할 수 있다.

만약 같은 엔진을 여러 개의 이벤트 루프에서 공유하여야 한다면, poolclass를 NullPool로 설정하여 엔진이 어떤 커넥션도 두 번 이상 사용하지 못하도록 해야한다.

```
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@host/dbname",
    poolclass=NullPool,
)
```

# Using asyncio scoped session


# Using the Inspector to inspect schema objects
SQLAlchemy는 asyncio 버전의 Inspector를 제공하지 않는다. 하지만 AsyncConnection의 run_sync() 메서드를 활용함으로써 asyncio 컨텍스트에서 기존 인터페이스를 사용할 수 있다.

```
import asyncio

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine("postgresql+asyncpg://scott:tiger@localhost/test")


def use_inspector(conn):
    inspector = inspect(conn)
    # use the inspector
    print(inspector.get_view_names())
    # return any value to the caller
    return inspector.get_table_names()


async def async_main():
    async with engine.connect() as conn:
        tables = await conn.run_sync(use_inspector)


asyncio.run(async_main())
```

[Reflecting Database Objects](https://docs.sqlalchemy.org/en/20/core/reflection.html#metadata-reflection)
[Runtime Inspection API](https://docs.sqlalchemy.org/en/20/core/inspection.html)

# Engine API Documentation
