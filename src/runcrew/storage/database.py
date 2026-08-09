from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from runcrew.storage.models import Base


class Database:
    def __init__(self, url: str = "sqlite:///data/runcrew.db") -> None:
        if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
            database_path = Path(url.removeprefix("sqlite:///"))
            database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, future=True)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        if self.engine.dialect.name == "sqlite":
            with self.engine.begin() as connection:
                connection.exec_driver_sql("PRAGMA optimize")

    def session(self) -> Session:
        return self.session_factory()
