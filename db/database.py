from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///planner.db"

engine = create_engine(
    DATABASE_URL,
    echo=True,  # mostra queries (ótimo pra debug)
    future=True
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)