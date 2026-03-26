from db.database import engine
from db.base import Base

# importa todos os models
from models import *

def init_db():
    Base.metadata.create_all(bind=engine)