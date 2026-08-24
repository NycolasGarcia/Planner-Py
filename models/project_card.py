from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship, backref
from datetime import datetime

from db.base import Base


class Card(Base):
    __tablename__ = "project_cards"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    # Limitada a 200 chars (ver routes/projects.py _apply_card_fields) — não
    # é renderizada por inteiro no mini-card, só um resumo curto.
    description = Column(Text, nullable=True)
    rank = Column(Integer, nullable=True)

    # Sem color/icon próprios — a faixa lateral do mini-card vem do rank
    # (ver templates/project_board.html), nunca de uma cor/ícone livre por
    # card (removidos: não tinham uso visual em lugar nenhum do board).
    column_id = Column(Integer, ForeignKey("project_columns.id"), nullable=False)
    notes_id = Column(Integer, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)

    # Prazo próprio do card — diferente de Task (sem prazo próprio, só a
    # TaskList tem), Card é a unidade de trabalho de verdade dentro do board
    # (mesmo padrão de TaskList.event_id — ver models/task_list.py).
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)

    # unique=True: um card tem NO MÁXIMO uma tasklist (era o inverso antes —
    # TaskList.card_id — o que deixava N tasklists apontarem pro mesmo card
    # sem nada impedir). Card sem tasklist não tem prazo próprio nenhum.
    tasklist_id = Column(Integer, ForeignKey("task_lists.id", ondelete="SET NULL"), nullable=True, unique=True)

    order = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Sem cascade/single_parent de propósito: apagar o Card NUNCA apaga a
    # TaskList vinculada (ela sobrevive, só perde o vínculo — o FK acima já
    # tem ondelete="SET NULL" pro sentido contrário, apagar a TaskList
    # desvincula o card automaticamente). TaskList é reaproveitável fora do
    # board, então não é "dependente" do Card do jeito que Card.tasklist_id
    # sugere à primeira vista.
    # backref precisa de uselist=False explícito nos DOIS lados: sem isso o
    # SQLAlchemy não sabe que tasklist_id é unique (1 tasklist <-> no máximo
    # 1 card) e infere o lado reverso (TaskList.card) como lista.
    task_list = relationship("TaskList", backref=backref("card", uselist=False), uselist=False)