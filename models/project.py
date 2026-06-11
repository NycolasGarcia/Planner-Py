from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
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

    notes_id = Column(Integer, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)


    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    columns = relationship(
        "Column",
        backref="project",
        cascade="all, delete-orphan",
        order_by="Column.order"
    )