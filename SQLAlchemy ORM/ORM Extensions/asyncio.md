# Study Asynchronous I/O
* Link: [https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#synopsis-orm]

# Synopsis - Core
# Synpsis - ORM
## Preventing Implicit I/O when Using AsyncSession
- Implicit I/O
  - happens for example, a database query, may occur implicitly when accessing a related object or collection.
  - when using lazy-loaded relationships
- Why it's important to prevent it?
  - to prevent unexpected and inefficient database accesses + improve the performance and scalability of the application

- Techniques to prevent implicit I/O
  - Collections -> [Write Only Relationships](https://docs.sqlalchemy.org/en/20/orm/large_collections.html#write-only-relationship), [Querying Items](https://docs.sqlalchemy.org/en/20/orm/large_collections.html#querying-items)
  - Lazy-loaded relationship with more care
    - declare relationships with lazy="raise"
    - use eager loading to load collections
      - [selectinload()](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html#sqlalchemy.orm.selectinload)
  - Set Session.expire_on_commit = False
  - Use [AsyncSession.refresh()](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.AsyncSession.refresh) to load lazy-loaded relationship explicitly under asyncio
  
## Running Synchronous Methods and Functions under ayncio
- [AsyncSession.run_sync()](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.AsyncSession.run_sync)
  - run Python function inside of greenlet
  - greenlet will translate traditional synchronous programming concepts to use await when reaching the database driver
# Using events with the asyncio extension
- Events can be registered at the instance, class and sessionmaker level
## Examples of Event Listeners wth Async Engines / Sessions / Sessionmakers
- Core Events on AsyncEngine
- ORM Events on AsyncSession
- ORM Events on async_sessionmaker
- Asyncio and Events
- 
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


## Using awaitable-only driver methods in connection pool and other events
## Using multiple asyncio event loops
- What could happen if the same engine is shared in different event loops?
  - the ORM engine maintains stateful connections to the database, and it could interfere with each other's state
  - leading to inconsistent data, concurrency issues and etc.
- The application should not let multiple event loops share same AsyncEngine when using default pool implementation.
- Disabling pooling using [NullPool](https://docs.sqlalchemy.org/en/20/core/pooling.html#sqlalchemy.pool.NullPool) prevents the engine from using any connection more than once.

## Using asyncio scoped session
- What happens if the application uses the scoped pattern?
- [Contextual/Thread-local Sessions](https://docs.sqlalchemy.org/en/20/orm/contextual.html#unitofwork-contextual)

## Using the Inspector to inspect schema objects
- [Reflecting Database Objects](https://docs.sqlalchemy.org/en/20/core/reflection.html#metadata-reflection)
