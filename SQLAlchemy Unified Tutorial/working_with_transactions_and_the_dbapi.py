from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

engine = create_engine("sqlite+pysqlite:///:memory:", echo=True)

with engine.connect() as conn:
    result = conn.execute(text("SELECT 'Hello World'"))
    print(result.all())

# "commit as you go"
with engine.connect() as conn:
    conn.execute(text("CREATE TABLE some_table (x int, y int)"))
    conn.execute(
        text("INSERT INTO some_table (x, y) VALUES (:x, :y)"),
        [{"x": 1, "y": 1}, {"x": 2, "y": 4}],
    )

# "begin once"
with engine.begin() as conn:
    conn.execute(
        text("INSERT INTO some_table (x, y) VALUES (:x, :y)"),
        [{"x": 6, "y": 8}, {"x": 9, "y": 10}],
    )

with engine.connect() as conn:
    result = conn.execute(text("SELECT x, y FROM some_table WHERE y > :y"), {"y": 2})
    for x, y in result:
        print(f"x: {x}  y: {y}")

stmt = text("SELECT x, y FROM some_table WHERE y > :y ORDER BY x, y")
with Session(engine) as session:
    result = session.execute(stmt, {"y": 2})
    for x, y in result:
        print(f"x: {x}  y: {y}")

with Session(engine) as session:
    resultu = session.execute(
        text("UPDATE some_table SET y = :y WHERE x = :x"),
        [{"x": 11, "y": 15}, {"x": 12, "y": 16}],
    )
    session.commit()
