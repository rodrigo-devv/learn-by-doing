"""Configuração do banco de dados.

Por padrão usa SQLite (arquivo local). Para ir à nuvem depois, basta definir
a variável de ambiente DATABASE_URL (ex: Postgres) — nenhuma mudança de código.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# learning-by-doing/akademia.db (default). Sobrescrevível por env var.
# Usamos "or" (não o default do get) para que uma DATABASE_URL VAZIA — comum
# quando a referência ${{Postgres.DATABASE_URL}} não resolve no Railway —
# caia no SQLite em vez de quebrar o boot com "Could not parse URL from ''".
_DB_PATH = Path(__file__).resolve().parents[2] / "akademia.db"
DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{_DB_PATH}"

# O Railway (e outros) fornecem a URL como "postgres://" ou "postgresql://".
# O SQLAlchemy precisa do driver explícito: usamos psycopg (v3).
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# check_same_thread só é necessário/aceito pelo SQLite.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# pool_pre_ping evita conexões mortas em bancos gerenciados na nuvem.
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Classe base para todos os modelos do ORM."""


def get_db():
    """Dependency do FastAPI: abre uma sessão por requisição e fecha no fim."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
