from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, Time, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from db.base import Base


class Event(Base):
    __tablename__ = "events"

#Essenciais
    id = Column(Integer, primary_key=True, index=True)
    
    name = Column(String, nullable=False)

# Customização
    color = Column(String, nullable=False)
    icon = Column(String, nullable=True)
    
# Data + Horário
    date_start = Column(Date, nullable=False, index=True)
    
    time_start = Column(Time, nullable=True)
    time_end = Column(Time, nullable=True)

# Recorrência
    recurrence_enabled = Column(Boolean, default=False, nullable=False)       #True ou False

    recurrence_type = Column(String, nullable=True)                     # "daily", "weekly", "monthly" ou "yearly"
    recurrence_end = Column(Date, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    notes_id = Column(Integer, ForeignKey("notes.id"), nullable=True)    #Associar nota a esse evento
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)    #Associar task a esse evento

    notes = relationship("notes", backref="events")                       # 
    task = relationship("Task", backref="events")                       #