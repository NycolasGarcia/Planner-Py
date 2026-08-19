from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, Time, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from db.base import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    # Nullable igual Note.color: sem cor = segue a Cor Principal do sistema
    # (accent), não é mais obrigatório escolher uma cor da paleta fixa.
    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)

    date_start = Column(Date, nullable=False, index=True)
    time_start = Column(Time, nullable=True)
    time_end = Column(Time, nullable=True)

    # Duração em dias consecutivos a partir da data de início (ou de cada
    # ocorrência, se recorrente) — NULL/1 = evento de um dia só. O horário
    # (time_start/time_end) se repete IGUAL em cada um desses dias (faixa
    # diária, não um bloco contínuo sem interrupção entre os dias).
    duration_days = Column(Integer, nullable=True)

    recurrence_enabled = Column(Boolean, default=False, nullable=False)
    recurrence_type = Column(String, nullable=True)       # "interval" | "weekdays" | "monthday" | "yearday"
    recurrence_end = Column(Date, nullable=True)
    recurrence_interval = Column(Integer, nullable=True)  # a cada N dias
    recurrence_weekdays = Column(String, nullable=True)   # "0,2,4" (0=seg, 6=dom)
    recurrence_monthdays = Column(String, nullable=True)  # "4,6,12" (dias fixos do mês: 1–31)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    notes_id = Column(Integer, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)

    note = relationship("Note", backref="events")
    task = relationship("Task", backref="event", uselist=False)