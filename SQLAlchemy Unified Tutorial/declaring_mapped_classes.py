from sqlalchemy import Column, ForeignKey, Integer, String, engine
from sqlalchemy.orm import registry, relationship

engine = engine.create_engine("sqlite+pysqlite:///:memory:", echo=True)
mapper_registry = registry()
Base = mapper_registry.generate_base()


class User(Base):
    __tablename__ = "user_account"
    id = Column(Integer, primary_key=True)
    name = Column(String(length=30))
    fullname = Column(String)
    addresses = relationship("Address", back_populates="user")

    def __repr__(self):
        return f"User(id={self.id!r}, name={self.name!r}, fullname={self.fullname!r})"


class Address(Base):
    __tablename__ = "address"
    id = Column(Integer, primary_key=True)
    email_address = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("user_account.id"))
    user = relationship("User", back_populates="addresses")

    def __repr__(self):
        return f"Address(id={self.id!r}, email_address={self.email_address!r})"


mapper_registry.metadata.create_all(engine)
mapper_registry.metadata.drop_all(engine)
