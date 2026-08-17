from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from db.base import Base


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String, nullable=False)
    text = Column(Text, nullable=True)

    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)

    order = Column(Integer, nullable=False)

    is_pinned = Column(Boolean, nullable=True)

    folder_id = Column(Integer, ForeignKey("note_folders.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=True)

    # Preenchido quando a nota vai pra Lixeira (pasta de sistema) — controla
    # a contagem de retenção antes da exclusão permanente automática.
    deleted_at = Column(DateTime, nullable=True)