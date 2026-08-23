from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from db.base import Base


class Card(Base):
    __tablename__ = "project_cards"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    rank = Column(Integer, nullable=True)

    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)

    column_id = Column(Integer, ForeignKey("project_columns.id"), nullable=False)
    notes_id = Column(Integer, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)

    # unique=True: um card tem NO MÁXIMO uma tasklist (era o inverso antes —
    # TaskList.card_id — o que deixava N tasklists apontarem pro mesmo card
    # sem nada impedir). Card sem tasklist não tem prazo próprio nenhum.
    tasklist_id = Column(Integer, ForeignKey("task_lists.id", ondelete="SET NULL"), nullable=True, unique=True)

    order = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    task_list = relationship(
        "TaskList",
        backref="card",
        uselist=False,
        single_parent=True,
        cascade="all, delete-orphan",
    )