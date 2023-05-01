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

기존의 asyncio를 사용하여 애플리케이션은 IO-on-attribute access가 발생할 수 있는 어떤 지점을 피할 수 있도록 해야한다. 이를 위한 기술은 다음과 같으며, 몇몇은 이 전의 사례에 설명되어 있다.

- 컬렉션은 SQLAlchemy 2.0의 Write Only Relationships를 사용해 write only collection으로 대체될 수 있다. write only collection은 절대로 암시적인 IO를 발생시키기 않는다. 이 기능을 사용하면 컬렉션은 읽히지 않고, 명시적인 SQL 호출을 통해서만 쿼리할 수 있다. asyncio와 함께 사용되는 write-only collection의 예는 Asyncio Integration 섹션의 async_orm_writeonly.py를 참고하면 된다.

쓰기 전용 컬렉션을 사용하면, 컬렉션에 대한 프로그램의 동작을 간단하고 쉽게 예측할 수 있다. 그러나, 단점은 이러한 많은 컬렉션을 한 번에 로드하기 위한 빌트인 시스템이 없다는 것이다. 따라서 많은 컬렉션을 한 번에 로드하기 위해서는 수동으로 수행해야 한다. 따라서 이하의 글머리 기호 중 다수는  asyncio 와 지연 로드 관계 사용할 때 사용하는 특정 기술을 다루고 있다. 이러한 기술을 다룰 때는 더 많은 주의가 필요하다.

- 지연 로딩에 종속된 기존의 ORM 관계를 다룰 때에는, lazy="raise"로 관계를 선언함으로써 기본적으로 SQL을 내보내지 않도록 설정할 수 있다. 컬렉션을 로드하려면 모든 경우 즉시 로드를 사용해야 한다.

- 가장 유용한 즉시 로드 전략은 selectinload() eager loder이다. 이전 예시에서 await session.execute() 스코프 하에서 A.bs 컬렉션을 즉시 로드하기 위해 사용된 바 있다.

```

stmt = select(A).options(selectinload(A.bs))

```

- 새 객체를 생성할 때는, 컬렉션은 항상 위 예에 있는 목록과 같은 빈 객체로 할당된다.

```

A(bs=[], data="a2")

```

이는 A 객체가 플러쉬 될 때, A객체의 .bs 컬렉션이 존재하도록 하며 읽을 수 있도록 한다. 그렇지 않으면 A가 플러쉬 될 때 .bs 는 로드되지 않고 접근 시 에러가 발생하게 될 것이다.

- AsyncSession은 구성될 때 Session.exprire_on_commit = False로 설정된다. 이는 AsyncSession.commit()이 실행된 이후에 객체의 속성에 접근할 수 있도록 하기 위함이다.

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

기타 가이드라인은 이하를 포함한다:
- 세션 만료가 절대적으로 필요한 것이 아니라면 AsyncSession.refresh()를 사용하하기 위해 AsyncSession.expire()를 사용하는 것을 피해야 한다. asyncio를 사용하는 경우 Session.expire_on_commit 이 보통 False로 설정되어 있기 때문에 만료일반적으로 필요하지 않다.

- 지연 로딩 관계는 AsyncSession.refresh()를 사용하면 명시적으로 asyncio에서 로드될 수 있습니다. 이 경우 접근하려는 속성의 이름이 Session.refresh.attribute_names에 명시적으로 전달되어야 한다.

```
# assume a_obj is an A that has lazy loaded A.bs collection
a_obj = await async_session.get(A, [1])

# force the collection to load by naming it in attribute_names
await async_session.refresh(a_obj, ["bs"])

# collection is present

print(f"bs collection: {a_obj.bs}")
```

몰론 컬렉션을 이미 불러올 수 있는 즉시 로딩을 사용하는 것이 좋다.

- cascade 기능들을 명시적으로 나열하기 위해서 all cascade 옵션을 사용하는 것을 지양해야 한다. all cascade 옵션은 무엇보다 refresh-expire 설정을 의미한다. 이는 AsyncSession.refresh() 메서드가 관계된 객체의 속성을 만료하지만, relationship()에서 즉시 로딩이 설정되지 않았다고 가정하기 때문에 속성을 refresh하지 않고 만료된 상태로 남겨둔다.

- 위에 적힌 바와 같이 relationship() 구성에 더하여 deferred() 컬럼에 적절한 로더 옵션이 적용되어야 한다. Limiting which Colomns Load with Column Deferral을 참고하라.

- Dynamic Relationship Loaders의 "동적" 관계 로더 전략은 기본적으로 asyncio 접근 방식과 호환되지 않는다. 이 전략은 AsyncSession.run_sync() 메서드에 의해서 호출되거나 .statement 속성으로 일반적인 select 문을 실행하는 경우에 직접 사용할 수 있다.


```

user = await session.get(User, 42)
addresses = (await session.scalars(user.addresses.statement)).all()
stmt = user.addresses.statement.where(Address.email_address.startswith("patrick"))
addresses_filter = (await session.scalars(stmt)).all()

```

SQLAlchemy 2.0에 도입된 write only 기술은 asyncio와 완전히 호환 가능하며, 사용되어야 한다.

- 만약 MySQL8과 같이 RETURNING을 지원하지 않는 데이터베이스와 함께 asyncio를 사용하는 경우, 타임스탬프와 같은 서버 기본 값들은 새로 플러쉬된 객체에 사용될 수 없다. 이 경우 Mapper.eager_defaults 옵션이 사용되어야 한다. SQLAlchemy 2.0에서는 이러한 동작이 행이 삽입될 때  RETURNING을 이용하여 새로운 값을 가져오는 PostgreSQL, SQLite and MariaDB와 같은 백엔드에 자동으로 적용된다.

## Running Synchronous Methods and Functions under asyncio

기존 SQLAlchemy의 지연 로딩을 asyncio 이벤트 루프와 통합하는 대체 수단으로, AsyncSession.run_sync()라는 선택적 메서드가 제공된다. 이 메서드는 greenlet 내부에서 어떤 파이썬 함수든 실행시키는데, greenlet에서는 기존의 동기 프로그래밍 개념이 데이터베이스 드라이버에 접근할 때 await을 사용할 수 있도록 변환되도록 한다. 가설적인 접근 방식은 asyncio 지향 애플리케이션은 데이터베이스 관련 메서드를 AsyncSession.run_sync()를 사용하는 함수가 실행되는 것으로 패키징할 수 있다는 것이다.

위의 예시를 바꾸어, 만약 A.bs 컬렉션을 로드하는데 selectinload()을 사용하지 않는다면, 우리는 별도의 함수 내에서 속성에 대한 엑세스를 처리할 수 있다.

```

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


def fetch_and_update_objects(session):
    """run traditional sync-style ORM code in a function that will be
    invoked within an awaitable.

    """

    # the session object here is a traditional ORM Session.
    # all features are available here including legacy Query use.

    stmt = select(A)

    result = session.execute(stmt)
    for a1 in result.scalars():
        print(a1)

        # lazy loads
        for b1 in a1.bs:
            print(b1)

    # legacy Query use
    a1 = session.query(A).order_by(A.id).first()

    a1.data = "new data"


async def async_main():
    engine = create_async_engine(
        "postgresql+asyncpg://scott:tiger@localhost/test",
        echo=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        async with session.begin():
            session.add_all(
                [
                    A(bs=[B(), B()], data="a1"),
                    A(bs=[B()], data="a2"),
                    A(bs=[B(), B()], data="a3"),
                ]
            )

        await session.run_sync(fetch_and_update_objects)

        await session.commit()

    # for AsyncEngine created in function scope, close and
    # clean-up pooled connections
    await engine.dispose()


asyncio.run(async_main())

```

특정 함수를 "동기적"으로 실행하는 위의 접근법은 이벤트 기반 프로그래밍 라이브러리, 예를 들어 gevent와 같은 것 위에서 실행되는 SQLAlchemy 애플리케이션과 유사하다. 차이점은 아래와 같다.

1. gevent와 달리, 우리는 gevent 이벤트 루프에 통합할 필요 없이 기본 파이썬 asyncio 이벤트 루프 또는 어떠한 커스텀 이벤트 루프를 사용할 수 있다.

2. "monkeypatching"은 전혀 없다. 위의 예시는 실제 asyncio 드라이버를 사용하고 있으며 SQLAlchemy 커넥션 풀 역시 파이썬 내장 asyncio.Queue로 커넥션 풀링을 하고 있다.

3. 프로그램은 자유롭게, 사실상 성능 저하 없이 async/await 코드와 동기 코드를 사용하는 함수를 전환할 수 있다. 추가적으로 사용중인 "thread executor", waiters, 또는 synchronization은 존재하지 않는다.

# Using events with the asyncio extension
SQLAlchemy 이벤트 시스템은 asyncio extension을 통해 직접적으로 노출되지는 않는다. 즉 "async" 버전의 SQLAlchemy 이벤트 핸들러는 아직 없다.

그러나, asyncio extension이 동기적 SQLAlchemy API를 감싸고 있기 때문에, 보통의 "동기적인" 스타일의 이벤트 핸들러는 asyncio가 사용되지 않은 것처럼 언제나 자유롭게 사용할 수 있다.

아래에 상세히 설명된 바와 같이, 현재는 asyncio-facing API 이벤트를 등록하기 위해 두 가지 전략이 존재한다.

- 이벤트는 프록시 객체를 참조하는 sync 속성과 연결함으로써 인스턴스 레벨(예를 들어 특정 AsyncEngine 인스턴스)에서 등록될 수 있다. 예를 들어 PoolEvents.connect() 이벤트를 AsyncEngine 인스턴스에 등록하고 싶다면, AsyncEngine.sync_engine 속성을 타겟으로 활용할 수 있다. 타겟은 다음을 포함한다: AsyncEngine.sync_engine , AsyncConnection.sync_connection, AsyncConnection.sync_engine, AsyncSession.sync_session

- 동일한 모든 유형의 인스턴스를 타겟으로 클래스 레벨에서 이벤트를 등록하기 위해서는 매칭되는 sync-style의 클래스를 사용한다. 예를 들어서 SessionEvents.before_commit() 이벤트를 AsyncSession 클래스에 등록하기 위해서는 Session 클래스를 타켓으로 사용한다.

- sessionmaker 레벨에서 등록하기 위해서는, async_sessionmaker.sync_session_class을 활용하여 명시적인 sessionmaker와 async_sessionmaker를 통합하고, 이벤트를 sessionmaker와 연결한다.

asyncio context 하의 이벤트 핸들러 내에서 작업할 때에는, Connection과 같은 객체는 await 또는 async하게 사용할 필요 없이, 보통의 "동기적"인 방법으로 계속 동작한다. 메시지가 최종적으로 asyncio database adapter가 메시지를 최정적으로 받게 되면, 호출 방식이 투명하게 asyncio 호출 방식으로 조정된다. DBAPI 수준의 커넥션을 전달하는 이벤트, 가령 PoolEvents.connect()와 같은 경우, 객체는 pep-249에 부합하는 "커넥션" 객체로서 asyncio 드라이버 내에서 sync-style 호출을 적용한다.

## Examples of Event Listeners with Async Engines / Sessions / Sessionmakers

async-facing API 구조체와 연결된 동기 스타일 이벤트 예시는 아래와 같다:

- Core Events on AsyncEngine
이 예시에서는, AsyncEngine의 AsyncEngine.sync_engine()을 ConnectionEvents와 PoolEvents의 타겟으로 접근한다.

```
import asyncio

from sqlalchemy import event
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine("postgresql+asyncpg://scott:tiger@localhost:5432/test")


# connect event on instance of Engine
@event.listens_for(engine.sync_engine, "connect")
def my_on_connect(dbapi_con, connection_record):
    print("New DBAPI connection:", dbapi_con)
    cursor = dbapi_con.cursor()

    # sync style API use for adapted DBAPI connection / cursor
    cursor.execute("select 'execute from event'")
    print(cursor.fetchone()[0])


# before_execute event on all Engine instances
@event.listens_for(Engine, "before_execute")
def my_before_execute(
    conn,
    clauseelement,
    multiparams,
    params,
    execution_options,
):
    print("before execute!")


async def go():
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    await engine.dispose()


asyncio.run(go())
```

- ORM Events on AsyncSession
이 예시에서는 SessionEvents의 타겟으로 AsyncSession.sync_session에 접근한다.

```
import asyncio

from sqlalchemy import event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session

engine = create_async_engine("postgresql+asyncpg://scott:tiger@localhost:5432/test")

session = AsyncSession(engine)


# before_commit event on instance of Session
@event.listens_for(session.sync_session, "before_commit")
def my_before_commit(session):
    print("before commit!")

    # sync style API use on Session
    connection = session.connection()

    # sync style API use on Connection
    result = connection.execute(text("select 'execute from event'"))
    print(result.first())


# after_commit event on all Session instances
@event.listens_for(Session, "after_commit")
def my_after_commit(session):
    print("after commit!")


async def go():
    await session.execute(text("select 1"))
    await session.commit()

    await session.close()
    await engine.dispose()


asyncio.run(go())
```

```
before commit!
execute from event
after commit!
```

- ORM Events on async_sessionmaker
우리는 sessionmaker를 이벤트 타겟으로 만들고, async_sessionmaker.sync_session_class 파라미터를 활용해 async_sessionmaker에 할당한다.

```
import asyncio

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import sessionmaker

sync_maker = sessionmaker()
maker = async_sessionmaker(sync_session_class=sync_maker)


@event.listens_for(sync_maker, "before_commit")
def before_commit(session):
    print("before commit")


async def main():
    async_session = maker()

    await async_session.commit()


asyncio.run(main())
```

```
before commit
```

- asyncio and events, two opposites

SQLAlchemy 이벤트는 태생적으로 특정한 SQLAlchemy 프로세스 내에 위치한다. 이는 이벤트가 어떤 특정한 SQLAlchemy API가 end-user 코드에 의해 호출된 **이후** 항상 발생하고, 그 API의 다른 내부 측면이 발생하기 **이전**에 항상 발생한다는 것을 의미한다.

이를 asyncio extention의 아키텍처와 대조하라. asyncio extention은 end-user API에서 DBAPI 함수로 이어지는 SQLALchemy의 일반적인 흐름 외부에 위치한다.

```
 SQLAlchemy    SQLAlchemy        SQLAlchemy          SQLAlchemy   plain
  asyncio      asyncio           ORM/Core            asyncio      asyncio
  (public      (internal)                            (internal)
  facing)
-------------|------------|------------------------|-----------|------------
asyncio API  |            |                        |           |
call  ->     |            |                        |           |
             |  ->  ->    |                        |  ->  ->   |
             |~~~~~~~~~~~~| sync API call ->       |~~~~~~~~~~~|
             | asyncio    |  event hooks ->        | sync      |
             | to         |   invoke action ->     | to        |
             | sync       |    event hooks ->      | asyncio   |
             | (greenlet) |     dialect ->         | (leave    |
             |~~~~~~~~~~~~|      event hooks ->    | greenlet) |
             |  ->  ->    |       sync adapted     |~~~~~~~~~~~|
             |            |               DBAPI -> |  ->  ->   | asyncio
             |            |                        |           | driver -> database
```

위에서 API 호출은 항상 asyncio로 시작했다가 동기적 API를 통하고, 동일한 연쇄 작용이 반대로 작동하면서 결과가 전달되기 전에 asyncio로 끝난다. 그 사이에 메시지는 처음 sync-style의 API를 사용하도록 조정되고, async 스타일로 조정된다. 이벤트 훅은 그리고 나서 자연스럽게 "sync-style API use" 중간에 발생한다. 이것으로부터 훅에 존재하는 API는 asyncio API 리퀘스트가 동기화되도록 조정된 프로세스 내에서 발생하며, database API로 나가는 메시지들은 asyncio로 투명하게 변환된다.

## Using awaitable-only driver methods in connection pool and other events

위 섹션에서 논의된 바와 같이, 가령 PoolEvents에 기반한 이벤트 핸들러와 같은 핸들러는 sync-style의 "DBAPI" 커넥션을 받는다. 이 커넥션은 SQLAlchemy asyncio 방언에서 제공한 wrapper 객체로서, asyncio "driver" 커넥션을 SQLAlchemy internals에서 적용할 수 있도록 한다. 사용자가 정의한 이벤트 핸들러의 경우, 이러한 이벤트 핸들러가 최종적인 "driver" 커넥션을 직접 사용하기 위해서, awaitable only 메서드를 드라이버 커넥션에 사용하는 특별한 사용 사례가 생기게 된다. 한 예시로 asyncpg 드라이버가 제공하는 .set_type_codec() 메서드를 들 수 있다.

이 유스케이스를 적용하기 위해서, SQLAlchemy의 AdaptedConnection 클래스는 AdaptedConnection.run_async() 메서드를 제공한다. 이 메서드는 이벤트 핸들러의 "동기적" 컨텍스트 또는 다른 SQLAlchemy 내부에서 awaitable한 함수가 실행되도록 한다. 이 메서드는 AsyncConnection.run_sync() 메서드와 직접적으로 유사람을 보이는데, 이 메서드는 sync-style 메서드를 async 하에서 실행되도록 허용한다.

AdaptedConnection.run_async() 는 가장 안쪽의 "driver" 커넥션을 하나의 인자로 받아들이고 AdaptedConnection.run_async() 메서드에 의해 호출될 awaitable을 반환하는 함수를 전달해야 한다. 주어진 함수는 async로 선언될 필요는 없다. 파이썬 람다 함수여도 괜찮은데; awaitable한 값이 리턴 후에 호출될 것이기 때문이다:

```

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(...)


@event.listens_for(engine.sync_engine, "connect")
def register_custom_types(dbapi_connection, *args):
    dbapi_connection.run_async(
        lambda connection: connection.set_type_codec(
            "MyCustomType",
            encoder,
            decoder,  # ...
        )
    )

```

위 코드에서 register_custom_types 이벤트 핸들러에 전달된 객체는 AdaptedConnection 인스턴스로, 이하 async-only driver-level 커텍션 객체에 DBAPI-like 인터페이스를 제공한다. 그리고 나서 AdaptedConnection.run_async()는 그리고 driver level 커넥션이 작동할 수 있는 awaitale한 환경에 대한 접근을 제공하게 된다.

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

scoped_session 객체와 함께 쓰레드된 SQLAlchemy에 사용된 "scoped session" 패턴 역시 async_scoped_session을 이용해 asyncio에서 사용 가능하다.

Tip
SQLAlchemy는 보통 "scoped" 패턴을 새로운 개발 시 추천하지 않는데, 이는 쓰레드 또는 태스크가 끝났을 때 명시적으로 종료되는, 즉 변경되는 글로벌한 상태에 의존하게 되기 때문이다. 특히 asyncio를 사용할 때에는 AsyncSession을 awaitable한 함수에 전달하는 것이 더 좋은 접근법이다.

async_scoped_session을 사용할 때, "thread-local" 컨셉이 asyncio context에는 존재하지 않으므로, "scopefunc" 파라미터가 생성자에게 추가되어야 한다. 이하의 예시는 이러한 목적을 위해 asyncio.current_task()를 사용한다.

```

from asyncio import current_task

from sqlalchemy.ext.asyncio import (
    async_scoped_session,
    async_sessionmaker,
)

async_session_factory = async_sessionmaker(
    some_async_engine,
    expire_on_commit=False,
)
AsyncScopedSession = async_scoped_session(
    async_session_factory,
    scopefunc=current_task,
)
some_async_session = AsyncScopedSession()

```

async_scoped_session은 scoped_session의 것과 같은 proxy behavior을 포함한다. 이는 async_scoped_session이 AsyncSession처럼 다뤄질 수 있다는 것을 의미하는데, 보통 await 키워드와 async_scoped_session.remove() 메서드가 필요하다는 것을 기억하자.

```
async def some_function(some_async_session, some_object):
    # use the AsyncSession directly
    some_async_session.add(some_object)

    # use the AsyncSession via the context-local proxy
    await AsyncScopedSession.commit()

    # "remove" the current proxied AsyncSession for the local context
    await AsyncScopedSession.remove()
```
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
