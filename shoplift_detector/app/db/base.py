import logging
import os

from dotenv import load_dotenv
from psycopg2 import pool

load_dotenv()
logger = logging.getLogger(__name__)

_connection_pool = None


def _get_pool():
    global _connection_pool
    if _connection_pool is None:
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            _connection_pool = pool.SimpleConnectionPool(1, 10, dsn=db_url)
        else:
            _connection_pool = pool.SimpleConnectionPool(
                1, 10,
                dbname=os.getenv("DB_NAME", "postgres"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", ""),
                host=os.getenv("DB_HOST", "127.0.0.1"),
                port=os.getenv("DB_PORT", "5432"),
            )
    return _connection_pool


class BaseDB:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            self.conn_params = {
                "dbname": os.getenv("DB_NAME", "postgres"),
                "user": os.getenv("DB_USER", "postgres"),
                "password": os.getenv("DB_PASSWORD", ""),
                "host": os.getenv("DB_HOST", "127.0.0.1"),
                "port": os.getenv("DB_PORT", "5432")
            }

    def _get_connection(self):
        try:
            p = _get_pool()
            return p.getconn()
        except Exception as e:
            logger.error(f"DB Connection Error: {e}")
            return None

    def _return_connection(self, conn):
        try:
            p = _get_pool()
            p.putconn(conn)
        except Exception:
            pass
