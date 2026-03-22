import sqlite3
from pathlib import Path

from app.config import Config


def ensure_data_dir() -> None:
    Path(Config.DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_teslamate_conn():
    import psycopg2

    return psycopg2.connect(
        host=Config.TESLAMATE_DB_HOST,
        port=Config.TESLAMATE_DB_PORT,
        dbname=Config.TESLAMATE_DB_NAME,
        user=Config.TESLAMATE_DB_USER,
        password=Config.TESLAMATE_DB_PASSWORD,
    )


def get_app_db():
    ensure_data_dir()
    conn = sqlite3.connect(Config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn
