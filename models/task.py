from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Date
from sqlalchemy.orm import relationship
from datetime import datetime

from db.base import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)

    task_list_id = Column(Integer, ForeignKey("task_lists.id"), nullable=False)

    name = Column(String, nullable=False)

    # Sem cor/ícone/descrição próprios — herda visual da TaskList (ver
    # routes/tasks.py) e não tem campo de observação de texto livre.

    rank = Column(Integer, nullable=True)

    order = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=True)

    # Última ocorrência marcada como feita (não é um boolean: sem recorrência
    # é só "preenchido = feito"; com recorrência, "feito" vira comparar essa
    # data com a ocorrência mais recente que já devia ter acontecido — sem
    # precisar de nenhum processo rodando pra "resetar" nada à meia-noite).
    last_check = Column(Date, nullable=True)

    notes_id = Column(Integer, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)

    # Prazo = um Event de verdade, não uma data literal (ver models/event.py).
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)