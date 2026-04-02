import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

class BaseDB:
    def __init__(self):
        self.conn_params = {
            "dbname": os.getenv("DB_NAME"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "host": os.getenv("DB_HOST", "127.0.0.1"),
            "port": os.getenv("DB_PORT", "5432")
        }

    def _get_connection(self):
        try:
            return psycopg2.connect(**self.conn_params)
        except Exception as e:
            print(f" DB Connection Error: {e}")
            return None