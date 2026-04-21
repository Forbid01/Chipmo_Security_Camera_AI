import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _seconds_since(event_time: datetime) -> float:
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=UTC)
    return (datetime.now(UTC) - event_time).total_seconds()


class AlertRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._column_cache: dict[str, set[str]] = {}

    async def _get_table_columns(self, table_name: str) -> set[str]:
        if table_name not in self._column_cache:
            query = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :table_name
            """)
            result = await self.db.execute(query, {"table_name": table_name})
            self._column_cache[table_name] = {row[0] for row in result.fetchall()}
        return self._column_cache[table_name]

    async def _has_column(self, table_name: str, column_name: str) -> bool:
        return column_name in await self._get_table_columns(table_name)

    async def _build_alert_query_parts(
        self, organization_id: int = None, store_id: int = None
    ) -> tuple[str, dict[str, Any]]:
        alerts_columns = await self._get_table_columns("alerts")
        cameras_columns = await self._get_table_columns("cameras")
        has_alert_store_id = "store_id" in alerts_columns
        has_alert_camera_id = "camera_id" in alerts_columns
        has_camera_store_id = "store_id" in cameras_columns

        params: dict[str, Any] = {}
        conditions = []

        if organization_id:
            conditions.append("a.organization_id = :org_id")
            params["org_id"] = organization_id

        join_camera = has_alert_camera_id and has_camera_store_id
        if store_id:
            if has_alert_store_id:
                conditions.append("a.store_id = :store_id")
            elif join_camera:
                conditions.append("c.store_id = :store_id")
            else:
                conditions.append("1 = 0")
            params["store_id"] = store_id

        camera_join = "LEFT JOIN cameras c ON a.camera_id = c.id" if join_camera else ""
        if has_alert_store_id:
            store_select = "a.store_id AS store_id"
            store_join = "LEFT JOIN stores s ON a.store_id = s.id"
        elif join_camera:
            store_select = "c.store_id AS store_id"
            store_join = "LEFT JOIN stores s ON c.store_id = s.id"
        else:
            store_select = "NULL::integer AS store_id"
            store_join = ""

        select_parts = [
            "a.id",
            "a.person_id",
            "a.organization_id",
            store_select,
            "a.camera_id" if has_alert_camera_id else "NULL::integer AS camera_id",
            "a.event_time",
            "a.image_path",
            "a.video_path" if "video_path" in alerts_columns else "NULL::text AS video_path",
            "a.description",
            (
                "a.confidence_score"
                if "confidence_score" in alerts_columns
                else "NULL::double precision AS confidence_score"
            ),
            "a.reviewed",
            (
                "a.feedback_status"
                if "feedback_status" in alerts_columns
                else "CASE WHEN COALESCE(a.reviewed, FALSE) THEN 'reviewed' "
                     "ELSE 'unreviewed' END AS feedback_status"
            ),
            "o.name as organization_name",
            "s.name as store_name" if store_join else "NULL::text AS store_name",
        ]

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"""
            SELECT
                {", ".join(select_parts)}
            FROM alerts a
            LEFT JOIN organizations o ON a.organization_id = o.id
            {camera_join}
            {store_join}
            {where}
        """
        return query, params

    async def insert_alert(
        self,
        person_id: int,
        image_path: str,
        reason: str,
        organization_id: int = None,
        store_id: int = None,
        camera_id: int = None,
        confidence_score: float = None,
        video_path: str = None,
    ) -> int | None:
        alerts_columns = await self._get_table_columns("alerts")
        duplicate_conditions = ["person_id = :pid"]
        params: dict[str, Any] = {"pid": person_id}
        if camera_id is not None and "camera_id" in alerts_columns:
            duplicate_conditions.append("camera_id = :cam_id")
            params["cam_id"] = camera_id

        check = text(f"""
            SELECT event_time FROM alerts
            WHERE {" AND ".join(duplicate_conditions)}
            ORDER BY event_time DESC
            LIMIT 1
        """)
        result = await self.db.execute(check, params)
        last = result.fetchone()
        if last and _seconds_since(last[0]) < 10:
            return None

        column_values = [
            ("person_id", person_id, "pid"),
            ("image_path", image_path, "img"),
            ("description", reason, "desc"),
            ("organization_id", organization_id, "org_id"),
        ]

        optional_values = [
            ("store_id", store_id, "store_id"),
            ("camera_id", camera_id, "cam_id"),
            ("video_path", video_path, "vid"),
            ("confidence_score", confidence_score, "score"),
        ]

        for column_name, value, param_name in optional_values:
            if column_name in alerts_columns:
                column_values.append((column_name, value, param_name))

        columns = ", ".join(column_name for column_name, _, _ in column_values)
        values = ", ".join(f":{param_name}" for _, _, param_name in column_values)
        params = {param_name: value for _, value, param_name in column_values}

        query = text(f"""
            INSERT INTO alerts ({columns})
            VALUES ({values})
            RETURNING id
        """)
        result = await self.db.execute(query, params)
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def get_latest_alerts(
        self,
        organization_id: int = None,
        store_id: int = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query_sql, params = await self._build_alert_query_parts(organization_id, store_id)
        params.update({"limit": limit, "offset": offset})
        query = text(f"""
            {query_sql}
            ORDER BY a.event_time DESC LIMIT :limit OFFSET :offset
        """)
        result = await self.db.execute(query, params)
        rows = result.mappings().fetchall()
        alerts = []
        for row in rows:
            item = dict(row)
            if item.get("event_time"):
                item["event_time"] = item["event_time"].strftime("%Y-%m-%d %H:%M:%S")
            alerts.append(item)
        return alerts

    async def get_all_alerts_admin(
        self,
        organization_id: int = None,
        store_id: int = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query_sql, params = await self._build_alert_query_parts(organization_id, store_id)
        params.update({"limit": limit, "offset": offset})
        query = text(f"""
            {query_sql}
            ORDER BY a.event_time DESC LIMIT :limit OFFSET :offset
        """)
        result = await self.db.execute(query, params)
        rows = result.mappings().fetchall()
        alerts = []
        for row in rows:
            item = dict(row)
            if item.get("event_time"):
                item["event_time"] = item["event_time"].strftime("%Y-%m-%d %H:%M:%S")
            alerts.append(item)
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
        alerts_columns = await self._get_table_columns("alerts")
        if "feedback_status" in alerts_columns:
            query = text("""
                UPDATE alerts
                SET feedback_status = :status, reviewed = TRUE
                WHERE id = :id
            """)
            params = {"status": status, "id": alert_id}
        else:
            query = text("UPDATE alerts SET reviewed = TRUE WHERE id = :id")
            params = {"id": alert_id}

        result = await self.db.execute(query, params)
        await self.db.commit()
        return result.rowcount > 0
