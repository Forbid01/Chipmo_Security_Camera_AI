import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from app.db.base import BaseDB

class AlertRepository(BaseDB):
    def __init__(self):
        # BaseDB-ийн __init__-ийг дуудаж холболтын тохиргоог авна
        super().__init__()
        self._create_table()

    def _create_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS alerts (
            id SERIAL PRIMARY KEY,
            person_id INTEGER NOT NULL,
            organization_id INTEGER REFERENCES organizations(id), -- Энийг нэмнэ
            event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            image_path TEXT,
            description TEXT
        );
        """ 
        conn = self._get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(query)
                    conn.commit()
            except Exception as e:
                print(f" Alerts Table Creation Error: {e}")
            finally:
                conn.close()

    def insert_alert(self, person_id: int, image_path: str, reason: str):
        conn = self._get_connection()
        if not conn:
            return

        try:
            with conn.cursor() as cur:
                check_query = """
                SELECT event_time FROM alerts 
                WHERE person_id = %s 
                ORDER BY event_time DESC LIMIT 1
                """
                cur.execute(check_query, (person_id,))
                last_record = cur.fetchone()

                if last_record:
                    last_time = last_record[0]
                    if datetime.now() - last_time < timedelta(seconds=10):
                        return

                # 2. Шинэ рекорд оруулах
                insert_query = """
                INSERT INTO alerts (person_id, image_path, description)
                VALUES (%s, %s, %s)
                """
                cur.execute(insert_query, (person_id, image_path, reason))
                conn.commit()
                print(f" DB Saved: Person ID {person_id} - {reason}")
                
        except Exception as e:
            print(f" DB Insert Error: {e}")
        finally:
            conn.close()

    def get_latest_alerts(self, organization_id: int, limit: int = 20):
        # Зөвхөн тухайн байгууллагын alerts-ыг шүүж авна
        query = """
        SELECT * FROM alerts 
        WHERE organization_id = %s 
        ORDER BY event_time DESC LIMIT %s
        """
        conn = self._get_connection()
        if not conn: return []
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (organization_id, limit))
                rows = cur.fetchall()
                
                # Төгсгөлийн боловсруулалт: Датаг текст хэлбэрт шилжүүлэх
                for row in rows:
                    if row.get('event_time'):
                        row['event_time'] = row['event_time'].strftime("%Y-%m-%d %H:%M:%S")
                return rows
        except Exception as e:
            print(f" DB Select Error: {e}")
            return []
        finally:
            conn.close()