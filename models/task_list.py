from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean, DateTime, Date
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
    due_date = Column(Date, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    notes_id = Column(Integer, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)

    # Origem opcional (Kanban)
    card_id = Column(Integer, ForeignKey("project_cards.id"), nullable=True)

    # Relacionamentos
    tasks = relationship(
        "Task",
        backref="task_list",
        cascade="all, delete-orphan",
        order_by="Task.order"
    )