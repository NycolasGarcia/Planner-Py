from sqlalchemy import text

from db.database import engine
from db.base import Base

# importa todos os models
from models import *


def _add_column_if_missing(conn, table, column, ddl):
    # Base.metadata.create_all() só cria tabelas novas, nunca altera tabelas
    # já existentes — colunas adicionadas depois ao model precisam de
    # ALTER TABLE manual (projeto não usa Alembic).
    cols = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    if not any(c[1] == column for c in cols):
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _run_migrations():
    with engine.begin() as conn:
        _add_column_if_missing(conn, "notes", "folder_id",
                                "folder_id INTEGER REFERENCES note_folders(id)")
        _add_column_if_missing(conn, "note_folders", "is_pinned",
                                "is_pinned BOOLEAN")


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
    except KeyboardInterrupt:
        # SQLite DDL é atômico por statement — tabelas já existem.
        # Re-executa para garantir que todos os índices foram criados.
        Base.metadata.create_all(bind=engine)
    _run_migrations()