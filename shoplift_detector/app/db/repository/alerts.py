import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


class AlertRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def insert_alert(self, person_id: int, image_path: str, reason: str,
                           organization_id: int = None, store_id: int = None,
                           camera_id: int = None, confidence_score: float = None,
                           video_path: str = None) -> Optional[int]:
        # Deduplication: 10-second cooldown per person
        check = text("""
            SELECT event_time FROM alerts
            WHERE person_id = :pid ORDER BY event_time DESC LIMIT 1
        """)
        result = await self.db.execute(check, {"pid": person_id})
        last = result.fetchone()
        if last and (datetime.now() - last[0]).total_seconds() < 10:
            return None

        query = text("""
            INSERT INTO alerts (person_id, image_path, video_path, description,
                               organization_id, store_id, camera_id, confidence_score)
            VALUES (:pid, :img, :vid, :desc, :org_id, :store_id, :cam_id, :score)
            RETURNING id
        """)
        result = await self.db.execute(query, {
            "pid": person_id, "img": image_path, "vid": video_path,
            "desc": reason, "org_id": organization_id, "store_id": store_id,
            "cam_id": camera_id, "score": confidence_score,
        })
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def get_latest_alerts(self, organization_id: int = None,
                                store_id: int = None, limit: int = 20,
                                offset: int = 0) -> List[Dict[str, Any]]:
        conditions = []
        params = {"limit": limit, "offset": offset}

        if organization_id:
            conditions.append("a.organization_id = :org_id")
            params["org_id"] = organization_id
        if store_id:
            conditions.append("a.store_id = :store_id")
            params["store_id"] = store_id

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = text(f"""
            SELECT a.*, o.name as organization_name, s.name as store_name
            FROM alerts a
            LEFT JOIN organizations o ON a.organization_id = o.id
            LEFT JOIN stores s ON a.store_id = s.id
            {where}
            ORDER BY a.event_time DESC LIMIT :limit OFFSET :offset
        """)
        result = await self.db.execute(query, params)
        rows = result.mappings().fetchall()
        alerts = []
        for row in rows:
            d = dict(row)
            if d.get("event_time"):
                d["event_time"] = d["event_time"].strftime("%Y-%m-%d %H:%M:%S")
            alerts.append(d)
        return alerts

    async def get_all_alerts_admin(self, organization_id: int = None,
                                   store_id: int = None, limit: int = 50,
                                   offset: int = 0) -> List[Dict[str, Any]]:
        conditions = []
        params = {"limit": limit, "offset": offset}

        if organization_id:
            conditions.append("a.organization_id = :org_id")
            params["org_id"] = organization_id
        if store_id:
            conditions.append("a.store_id = :store_id")
            params["store_id"] = store_id

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = text(f"""
            SELECT a.*, o.name as organization_name, s.name as store_name
            FROM alerts a
            LEFT JOIN organizations o ON a.organization_id = o.id
            LEFT JOIN stores s ON a.store_id = s.id
            {where}
            ORDER BY a.event_time DESC LIMIT :limit OFFSET :offset
        """)
        result = await self.db.execute(query, params)
        rows = result.mappings().fetchall()
        alerts = []
        for row in rows:
            d = dict(row)
            if d.get("event_time"):
                d["event_time"] = d["event_time"].strftime("%Y-%m-%d %H:%M:%S")
            alerts.append(d)
        return alerts

    async def mark_alert_reviewed(self, alert_id: int) -> bool:
        query = text("UPDATE alerts SET reviewed = TRUE WHERE id = :id")
        result = await self.db.execute(query, {"id": alert_id})
        await self.db.commit()
        return result.rowcount > 0

    async def delete_alert(self, alert_id: int) -> bool:
        query = text("DELETE FROM alerts WHERE id = :id")
        result = await self.db.execute(query, {"id": alert_id})
        await self.db.commit()
        return result.rowcount > 0

    async def update_feedback_status(self, alert_id: int, status: str) -> bool:
        query = text("UPDATE alerts SET feedback_status = :status WHERE id = :id")
        result = await self.db.execute(query, {"status": status, "id": alert_id})
        await self.db.commit()
        return result.rowcount > 0
