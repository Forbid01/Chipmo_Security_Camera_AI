import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

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
            if self.db_url:
                return psycopg2.connect(self.db_url)
            
            return psycopg2.connect(**self.conn_params)
            
        except Exception as e:
            print(f" DB Connection Error: {e}")
            return None