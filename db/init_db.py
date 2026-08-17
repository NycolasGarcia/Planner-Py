from datetime import datetime

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
        _add_column_if_missing(conn, "notes", "updated_at",
                                "updated_at DATETIME")
        _add_column_if_missing(conn, "notes", "deleted_at",
                                "deleted_at DATETIME")
        _add_column_if_missing(conn, "note_folders", "is_system",
                                "is_system BOOLEAN")


def _seed_lixeira():
    # Idempotente: cria a pasta de sistema "Lixeira" só se nenhuma pasta
    # is_system ainda existir. order alto pra não competir com pastas do
    # usuário nos moves de reordenação normais.
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM note_folders WHERE is_system = 1")
        ).fetchone()
        if existing:
            return
        max_order = conn.execute(
            text("SELECT COALESCE(MAX(\"order\"), 0) FROM note_folders")
        ).scalar()
        conn.execute(
            text(
                'INSERT INTO note_folders (name, color, icon, "order", is_pinned, is_system, created_at) '
                "VALUES ('Lixeira', 'secondary', 'bi bi-trash', :order, 0, 1, :now)"
            ),
            {"order": max_order + 1, "now": datetime.utcnow().isoformat(sep=" ")},
        )


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
    except KeyboardInterrupt:
        # SQLite DDL é atômico por statement — tabelas já existem.
        # Re-executa para garantir que todos os índices foram criados.
        Base.metadata.create_all(bind=engine)
    _run_migrations()
    _seed_lixeira()