import os
from typing import Generator
from sqlmodel import SQLModel, Session, create_engine, select

# app/core/database.py
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:boleta2020020444@localhost:5432/obras"
)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Crea todas las tablas declaradas en SQLModel."""
    import app.models_base  # noqa: F401
    SQLModel.metadata.create_all(engine)

def get_session() -> Generator[Session, None, None]:
    """Inyección de dependencias para proveer la sesión de base de datos."""
    with Session(engine) as session:
        yield session
