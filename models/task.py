from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Date
from sqlalchemy.orm import relationship
from datetime import datetime

from db.base import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)

    task_list_id = Column(Integer, ForeignKey("task_lists.id"), nullable=False)

    name = Column(String, nullable=False)

    # Sem cor/ícone/descrição próprios — herda visual da TaskList (ver
    # routes/tasks.py) e não tem campo de observação de texto livre.

    rank = Column(Integer, nullable=True)

    order = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=True)

    # "Feito" simples: presença = feito, None = não feito. Task nunca tem
    # prazo/recorrência próprio (só a TaskList tem — ver models/task_list.py),
    # então não existe "ocorrência recorrente" pra comparar aqui.
    last_check = Column(Date, nullable=True)

    # Task só existe dentro da sua TaskList — sem ícone, cor, nota vinculada
    # ou prazo próprios (ver routes/tasks.py). Único vínculo possível é
    # task_list_id acima; visual e prazo vêm inteiramente da lista-mãe.