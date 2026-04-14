import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from app.db.base import BaseDB

logger = logging.getLogger(__name__)

class AlertRepository(BaseDB):
    def __init__(self):
        # BaseDB-ийн __init__-ийг дуудаж холболтын тохиргоог авна
        super().__init__()
        self._create_table()

    def _create_table(self):
        queries = [
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY,
                person_id INTEGER NOT NULL,
                organization_id INTEGER REFERENCES organizations(id),
                event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                image_path TEXT,
                description TEXT
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_alerts_org_id ON alerts(organization_id);",
            "CREATE INDEX IF NOT EXISTS idx_alerts_event_time ON alerts(event_time DESC);",
            "CREATE INDEX IF NOT EXISTS idx_alerts_person_id ON alerts(person_id);",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS reviewed BOOLEAN DEFAULT FALSE;",
        ]
        conn = self._get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    for q in queries:
                        cur.execute(q)
                    conn.commit()
            except Exception as e:
                logger.error(f"Alerts Table Creation Error: {e}")
            finally:
                self._return_connection(conn)

    def insert_alert(self, person_id: int, image_path: str, reason: str, organization_id: int = None):
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

                insert_query = """
                INSERT INTO alerts (person_id, image_path, description, organization_id)
                VALUES (%s, %s, %s, %s)
                """
                cur.execute(insert_query, (person_id, image_path, reason, organization_id))
                conn.commit()
                logger.info(f"DB Saved: Person ID {person_id} for Org {organization_id}")

        except Exception as e:
            logger.error(f"DB Insert Error: {e}")
        finally:
            self._return_connection(conn)

    def get_all_alerts_admin(self, organization_id: int = None, limit: int = 50, offset: int = 0):
        """Admin panel-д зориулсан бүх alert-уудыг авах"""
        if organization_id:
            query = """
            SELECT a.*, o.name as organization_name
            FROM alerts a
            LEFT JOIN organizations o ON a.organization_id = o.id
            WHERE a.organization_id = %s
            ORDER BY a.event_time DESC LIMIT %s OFFSET %s
            """
            params = (organization_id, limit, offset)
        else:
            query = """
            SELECT a.*, o.name as organization_name
            FROM alerts a
            LEFT JOIN organizations o ON a.organization_id = o.id
            ORDER BY a.event_time DESC LIMIT %s OFFSET %s
            """
            params = (limit, offset)

        conn = self._get_connection()
        if not conn:
            return []
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                for row in rows:
                    if row.get('event_time'):
                        row['event_time'] = row['event_time'].strftime("%Y-%m-%d %H:%M:%S")
                return rows
        except Exception as e:
            logger.error(f"Admin Alerts Fetch Error: {e}")
            return []
        finally:
            self._return_connection(conn)

    def mark_alert_reviewed(self, alert_id: int) -> bool:
        conn = self._get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE alerts SET reviewed = TRUE WHERE id = %s", (alert_id,))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Alert Review Error: {e}")
            return False
        finally:
            self._return_connection(conn)

    def delete_alert(self, alert_id: int) -> bool:
        conn = self._get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM alerts WHERE id = %s", (alert_id,))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Alert Delete Error: {e}")
            return False
        finally:
            self._return_connection(conn)

    def get_latest_alerts(self, organization_id: int = None, limit: int = 20, offset: int = 0):
        if organization_id:
            query = """
            SELECT * FROM alerts
            WHERE organization_id = %s
            ORDER BY event_time DESC LIMIT %s OFFSET %s
            """
            params = (organization_id, limit, offset)
        else:
            query = """
            SELECT * FROM alerts
            ORDER BY event_time DESC LIMIT %s OFFSET %s
            """
            params = (limit, offset)

        conn = self._get_connection()
        if not conn:
            return []

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()

                for row in rows:
                    if row.get('event_time'):
                        row['event_time'] = row['event_time'].strftime("%Y-%m-%d %H:%M:%S")
                return rows
        except Exception as e:
            logger.error(f"DB Select Error: {e}")
            return []
        finally:
            self._return_connection(conn)