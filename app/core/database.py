import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# URL de conexión a PostgreSQL (o SQLite local para pruebas rápidas)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./obras_publicas_dev.db"  # Cambia a: "postgresql://usuario:password@localhost:5432/obras_db"
)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependencia que provee una sesión de base de datos por petición HTTP."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()