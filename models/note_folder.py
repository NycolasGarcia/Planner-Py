from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime

from db.base import Base


class NoteFolder(Base):
    __tablename__ = "note_folders"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)

    order = Column(Integer, nullable=False)

    is_pinned = Column(Boolean, nullable=True)

    # Marca a pasta especial "Lixeira" — protegida contra edição/exclusão pelo
    # usuário e escondida do seletor "mover para pasta" (só chega lá via delete).
    is_system = Column(Boolean, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
