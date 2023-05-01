from mapped_classes import Address, User, engine, mapper_registry
from sqlalchemy import bindparam, select
from sqlalchemy.dialects.postgresql import insert

mapper_registry.metadata.create_all(engine)

# The insert() SQL Expression Construct
stmt = insert(User).values(name="spongebob", fullname="Spongebob Squarepants")

with engine.begin() as conn:
    result = conn.execute(stmt)
    print(f"inserted_primary_key: {result.inserted_primary_key}")

# INSERT usually generates the "values" clause automatically
with engine.begin() as conn:
    result = conn.execute(
        insert(User),
        [
            {"name": "sandy", "fullname": "Sandy Cheeks"},
            {"name": "patrick", "fullname": "Patrick Star"},
        ],
    )

scalar_subq = (
    select(User.id).where(User.name == bindparam("username")).scalar_subquery()
)

with engine.begin() as conn:
    result = conn.execute(
        insert(Address).values(user_id=scalar_subq),
        [
            {"username": "spongebob", "email_address": "spongebob@sqlalchemy.org"},
            {"username": "sandy", "email_address": "sandy@sqlalchemy.org"},
            {"username": "sandy", "email_address": "sandy@squirrelpower.org"},
        ],
    )

select_stmt = select(User.id, User.fullname + "@aol.com")
insert_stmt = insert(Address).from_select(["user_id", "email_address"], select_stmt)
