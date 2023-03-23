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
from sqlalchemy.orm import Mapped
from sqlalchemy import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import declarative_base


class Base(declarative_base):
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

    # Legacy query use
    a1 = session.query(A).order_by(A.id).first()
    a1.data = "new data"


async def async_main() -> None:
    engine = create_async_engine(
        "postgresql+asyncpg://scott:tiger@localhost/test",
        echo=True,
    )

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await insert_objects(async_session)
    await select_and_update_objects(async_session)

    await engine.dispose()

asyncio.run(async_main())
