
from sqlalchemy import text

from backend.app.db.database import engine

with engine.connect() as connection:
    result = connection.execute(text("SELECT current_database()"))
    database_name = result.scalar_one()


    print("Connected successfully!")
    print("Database name:", database_name)
