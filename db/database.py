import os
import sys

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def _resolve_db_path():
    # Android roda dentro do runtime do python-for-android — não existe
    # "diretório de trabalho atual" no sentido desktop, e o app só tem
    # escrita garantida (sem pedir permissão) na própria storage sandboxed.
    # sys.getandroidapilevel só existe rodando de fato dentro do p4a —
    # é a mesma checagem que o próprio pywebview usa (webview/guilib.py)
    # pra escolher o backend Android sozinho.
    if hasattr(sys, 'getandroidapilevel'):
        from android.storage import app_storage_path
        return os.path.join(app_storage_path(), 'planner.db')
    # Desktop (dev): caminho relativo, resolve pro diretório de onde
    # `python app.py` é chamado — problema separado (empacotamento via
    # PyInstaller etc.), ainda não é o caso hoje.
    return 'planner.db'


DATABASE_URL = f"sqlite:///{_resolve_db_path()}"

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


# SQLite ignora FK por padrão em CADA conexão (não é uma config global do
# arquivo) — sem isso, todo "ondelete=SET NULL" declarado nos models (Event,
# Task, TaskList, Project...) é só decoração no schema, nunca roda de
# verdade. Sem isso, apagar uma nota referenciada em outro lugar (ex: via
# Note.__table__.delete() na Lixeira) deixava notes_id órfão apontando pra
# uma linha que não existe mais, em vez de virar NULL sozinho.
@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()