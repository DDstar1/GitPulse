from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine

DATABASE_URL = "sqlite:///gitpulse.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def _migrate_existing_columns() -> None:
    with engine.connect() as conn:
        existing_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(project)"))
        }
        if "launch_command" not in existing_columns:
            conn.execute(text("ALTER TABLE project ADD COLUMN launch_command TEXT"))
            conn.commit()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_existing_columns()


def get_session():
    with Session(engine) as session:
        yield session
