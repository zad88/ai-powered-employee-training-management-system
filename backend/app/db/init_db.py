
from backend.app.db.base import Base
from backend.app.db.database import engine
from backend.app.db import models


def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")


if __name__ == "__main__":
    init_db()
