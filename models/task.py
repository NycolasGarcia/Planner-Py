from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean, DateTime, Date
from sqlalchemy.orm import relationship
from datetime import datetime

from db.base import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)

    task_list_id = Column(Integer, ForeignKey("task_lists.id"), nullable=False)

    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)

    is_completed = Column(Boolean, default=False, nullable=False)

    rank = Column(Integer, nullable=True)

    order = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    due_date = Column(Date, nullable=True)

    notes_id = Column(Integer, ForeignKey("notes.id"), nullable=True)