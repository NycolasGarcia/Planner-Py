from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from db.base import Base


class TaskList(Base):
    __tablename__ = "task_lists"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)

    is_pinned = Column(Boolean, default=False, nullable=False)

    order = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=True)

    notes_id = Column(Integer, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)

    # Prazo = um Event de verdade, não uma data literal (ver models/event.py).
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)

    # Relacionamentos
    tasks = relationship(
        "Task",
        backref="task_list",
        cascade="all, delete-orphan",
        order_by="Task.order"
    )