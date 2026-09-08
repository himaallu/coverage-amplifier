import os
from collections.abc import Generator

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_TIMEOUT_SECONDS = 2


def get_database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def create_db_engine(url: str | None = None) -> sa.Engine:
    db_url = url or get_database_url()
    if not db_url:
        raise ValueError("DATABASE_URL is not set")

    connect_args: dict[str, int | str] = {}
    if db_url.startswith("postgresql"):
        # Set a short connect_timeout for psycopg
        connect_args["connect_timeout"] = DEFAULT_TIMEOUT_SECONDS
        return sa.create_engine(
            db_url,
            pool_size=5,
            max_overflow=0,
            pool_pre_ping=True,
            connect_args=connect_args,
        )

    return sa.create_engine(
        db_url,
        pool_pre_ping=True,
    )


def check_db_connection(url: str | None = None) -> bool:
    try:
        db_url = url or get_database_url()
        if not db_url:
            return False
        engine = create_db_engine(db_url)
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


def get_session_maker(engine: sa.Engine | None = None) -> sessionmaker[Session]:
    eng = engine or create_db_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=eng)


def get_db() -> Generator[Session, None, None]:
    session_factory = get_session_maker()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
