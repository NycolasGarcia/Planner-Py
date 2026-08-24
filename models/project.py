from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)

    is_pinned = Column(Boolean, default=False, nullable=False)

    # Preenchido quando o projeto vai pra Lixeira — mesmo esquema de
    # TaskList.deleted_at (ver models/task_list.py). Column/Card individuais
    # NUNCA passam por aqui: só o projeto (a coleção) tem lixeira própria.
    deleted_at = Column(DateTime, nullable=True)

    notes_id = Column(Integer, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)

    # Prazo = um Event de verdade, não uma data literal (ver models/event.py).
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    columns = relationship(
        "Column",
        backref="project",
        cascade="all, delete-orphan",
        order_by="Column.order"
    )