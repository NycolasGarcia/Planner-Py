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


def _migrate_events_drop_task_id(conn):
    # Event deixou de referenciar quem o usa como prazo (Task/TaskList/
    # Project.event_id é a direção certa agora — ver models/event.py).
    # SQLite recusa DROP COLUMN numa coluna que faz parte de uma FK ("error
    # in table events after drop column: unknown column ... in foreign key
    # definition") — só dá pra tirar recriando a tabela. Como já existem
    # eventos reais salvos, não dá pra só dropar (perderia os dados): renomeia
    # a tabela atual pro create_all() (chamado depois, no fim de
    # _run_migrations) recriar "events" do zero sem task_id, e
    # _finish_events_drop_task_id copia os dados de volta.
    cols = conn.execute(text("PRAGMA table_info(events)")).fetchall()
    if any(c[1] == "task_id" for c in cols):
        conn.execute(text("ALTER TABLE events RENAME TO events_old_task_id"))
        # Índices não trocam de nome junto com a tabela — sem isso o
        # create_all() bate de frente com o nome antigo (ix_events_date_start
        # "already exists") ao tentar recriar o índice na "events" nova.
        indexes = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='events_old_task_id' AND sql IS NOT NULL"
        )).fetchall()
        for (idx_name,) in indexes:
            conn.execute(text(f"DROP INDEX {idx_name}"))


def _finish_events_drop_task_id(conn):
    # Continuação de _migrate_events_drop_task_id — só faz sentido chamar
    # depois que Base.metadata.create_all() já recriou "events" do zero
    # (com o schema novo, sem task_id).
    tables = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='events_old_task_id'"
    )).fetchall()
    if not tables:
        return  # nada pra migrar
    cols = [c[1] for c in conn.execute(text("PRAGMA table_info(events)")).fetchall()]
    col_list = ", ".join(cols)
    conn.execute(text(f"INSERT INTO events ({col_list}) SELECT {col_list} FROM events_old_task_id"))
    conn.execute(text("DROP TABLE events_old_task_id"))


def _migrate_tasks_drop_own_visuals(conn):
    # Task deixou de ter cor/ícone/descrição próprios — herda visual da
    # TaskList (ver routes/tasks.py). Nenhuma das 3 colunas participa de FK,
    # então DROP COLUMN direto funciona (diferente do task_id de Event).
    cols = {c[1] for c in conn.execute(text("PRAGMA table_info(tasks)")).fetchall()}
    for col in ("color", "icon", "description"):
        if col in cols:
            conn.execute(text(f"ALTER TABLE tasks DROP COLUMN {col}"))


def _migrate_tasklists_add_order_and_updated_at(conn):
    # order: reordenar por arrastar na sidebar (mesmo padrão de Task.order,
    # que já existe). updated_at: sort "Modificação", igual Notas. Nenhuma
    # tasklist real tinha esses campos antes — backfill por created_at pra
    # a ordem inicial já nascer coerente (não é NULL/0 pra todo mundo).
    cols = {c[1] for c in conn.execute(text("PRAGMA table_info(task_lists)")).fetchall()}
    if "updated_at" not in cols:
        conn.execute(text("ALTER TABLE task_lists ADD COLUMN updated_at DATETIME"))
        conn.execute(text("UPDATE task_lists SET updated_at = created_at WHERE updated_at IS NULL"))
    if "order" not in cols:
        conn.execute(text('ALTER TABLE task_lists ADD COLUMN "order" INTEGER'))
        rows = conn.execute(text("SELECT id FROM task_lists ORDER BY created_at, id")).fetchall()
        for idx, (tl_id,) in enumerate(rows):
            conn.execute(text('UPDATE task_lists SET "order" = :o WHERE id = :id'), {"o": idx, "id": tl_id})


def _migrate_tasks_add_updated_at(conn):
    # Sort "Modificação" pras tasks, mesmo padrão de TaskList/Notas.
    cols = {c[1] for c in conn.execute(text("PRAGMA table_info(tasks)")).fetchall()}
    if "updated_at" not in cols:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN updated_at DATETIME"))
        conn.execute(text("UPDATE tasks SET updated_at = created_at WHERE updated_at IS NULL"))


def _reset_task_project_schema(conn):
    # tasks/task_lists/project_cards ainda não têm nenhuma rota de CRUD
    # (routes/tasks.py e routes/projects.py só renderizam a página vazia) —
    # sempre vazias na prática. Mais simples dropar e deixar o create_all()
    # final recriar do zero com o schema atual do model do que migrar
    # due_date/is_completed/card_id coluna por coluna (mesmo padrão já
    # usado em _relax_events_color_nullable). Guarda por uma coluna que só
    # existe no schema antigo, pra não dropar de novo em toda inicialização;
    # se por algum motivo a tabela não estiver vazia, só pula (não some com
    # dado real sem querer).
    old_schema_markers = {
        "tasks": "due_date",
        "task_lists": "card_id",
        "project_cards": "due_date",
    }
    for table, marker_col in old_schema_markers.items():
        cols = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        if not any(c[1] == marker_col for c in cols):
            continue  # já migrado
        count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if count == 0:
            conn.execute(text(f"DROP TABLE {table}"))


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
        _migrate_events_drop_task_id(conn)
        _reset_task_project_schema(conn)
        _migrate_tasks_drop_own_visuals(conn)
        _migrate_tasks_add_updated_at(conn)
        _migrate_tasklists_add_order_and_updated_at(conn)
        _add_column_if_missing(conn, "projects", "event_id",
                                "event_id INTEGER REFERENCES events(id)")
    # Recria as tabelas dropadas/renomeadas acima com o schema atual do
    # model (create_all só cria tabelas que não existem, não mexe nas outras).
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        _finish_events_drop_task_id(conn)


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