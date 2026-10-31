from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

# One connection string for the whole app: settings validates it the same way
# it validates every other secret, so a stray DATABASE_URL cannot bypass that.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # a recycled dead connection fails one query, not the request
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_pool_max_overflow,
    connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
