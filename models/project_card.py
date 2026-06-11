from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Date
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

    due_date = Column(Date, nullable=True)

    column_id = Column(Integer, ForeignKey("project_columns.id"), nullable=False)
    notes_id = Column(Integer, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)

    order = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    task_list = relationship(
    "TaskList",
    backref="card",
    uselist=False,
    cascade="all, delete-orphan"
)