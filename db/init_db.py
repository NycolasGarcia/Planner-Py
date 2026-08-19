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


def _migrate_events_monthday_to_monthdays(conn):
    # recurrence_monthday (int, 1 valor) virou recurrence_monthdays (string
    # "4,6,12", múltiplos valores — mesmo padrão de recurrence_weekdays).
    # Diferente da migração de color abaixo: já existem eventos reais salvos
    # (não dá mais pra dropar+recriar a tabela), então migra de verdade —
    # SQLite 3.35+ suporta DROP COLUMN direto (confirmado: 3.46.1 aqui).
    cols = conn.execute(text("PRAGMA table_info(events)")).fetchall()
    names = {c[1] for c in cols}
    if "recurrence_monthday" not in names:
        return  # já migrado
    if "recurrence_monthdays" not in names:
        conn.execute(text("ALTER TABLE events ADD COLUMN recurrence_monthdays VARCHAR"))
    conn.execute(text(
        "UPDATE events SET recurrence_monthdays = CAST(recurrence_monthday AS TEXT) "
        "WHERE recurrence_monthday IS NOT NULL AND recurrence_monthdays IS NULL"
    ))
    conn.execute(text("ALTER TABLE events DROP COLUMN recurrence_monthday"))


def _relax_events_color_nullable(conn):
    # events.color virou nullable (igual notes.color: sem cor = accent do
    # sistema), mas SQLite não faz ALTER COLUMN pra relaxar NOT NULL — a
    # tabela já existia (create_all cria pra todo model importado, mesmo
    # sem CRUD ainda existir). Só dropa+recria se estiver vazia (nunca
    # existiu API pra criar evento antes disso, deve estar sempre vazia).
    cols = conn.execute(text("PRAGMA table_info(events)")).fetchall()
    color_col = next((c for c in cols if c[1] == "color"), None)
    if color_col and color_col[3] == 1:  # notnull=1
        count = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
        if count == 0:
            conn.execute(text("DROP TABLE events"))


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
        _relax_events_color_nullable(conn)
        _migrate_events_monthday_to_monthdays(conn)
        _add_column_if_missing(conn, "events", "duration_days",
                                "duration_days INTEGER")
    # Recria a tabela dropada acima com o schema atual do model
    # (create_all só cria tabelas que não existem, não mexe nas outras).
    Base.metadata.create_all(bind=engine)


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