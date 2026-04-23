import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


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
        *,
        person_track_id: int | None = None,
        rag_decision: str | None = None,
        vlm_decision: str | None = None,
        suppressed: bool | None = None,
        suppressed_reason: str | None = None,
    ) -> int | None:
        # Deduplication is owned by AlertManager (alert_state table). This
        # repository trusts that the caller has already passed dedup; a
        # secondary 10s guard here would silently drop legitimate alerts
        # after AlertManager has already reserved the cooldown slot.
        alerts_columns = await self._get_table_columns("alerts")

        column_values: list[tuple[str, Any, str]] = [
            ("person_id", person_id, "pid"),
            ("image_path", image_path, "img"),
            ("description", reason, "desc"),
            ("organization_id", organization_id, "org_id"),
        ]

        # Optional legacy columns — include only when the caller supplied
        # a value AND the column exists. Keeps the query stable across
        # the pre-/post-migration schema window.
        optional_values: list[tuple[str, Any, str]] = [
            ("store_id", store_id, "store_id"),
            ("camera_id", camera_id, "cam_id"),
            ("video_path", video_path, "vid"),
            ("confidence_score", confidence_score, "score"),
        ]

        # Pipeline v2 columns (T02-14). Each is additive: the column
        # discovery guard below skips it on pre-migration schemas and
        # skips it when the caller didn't pass a value.
        pipeline_values: list[tuple[str, Any, str]] = [
            ("person_track_id", person_track_id, "ptid"),
            ("rag_decision", rag_decision, "rag"),
            ("vlm_decision", vlm_decision, "vlm"),
            ("suppressed", suppressed, "suppressed"),
            ("suppressed_reason", suppressed_reason, "suppressed_reason"),
        ]

        for column_name, value, param_name in (*optional_values, *pipeline_values):
            if column_name not in alerts_columns:
                continue
            if value is None:
                continue
            column_values.append((column_name, value, param_name))

        columns = ", ".join(column_name for column_name, _, _ in column_values)
        placeholders = [f":{param_name}" for _, _, param_name in column_values]
        values = ", ".join(placeholders)
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

    async def mark_suppressed(
        self,
        alert_id: int,
        *,
        reason: str,
        rag_decision: str | None = None,
        vlm_decision: str | None = None,
    ) -> bool:
        """Record a pipeline suppression decision on an already-inserted row.

        Used by the RAG/VLM stages that consume a persisted alert and
        need to mark it suppressed without re-inserting. Tolerates the
        pre-migration schema where the columns don't exist yet.
        """
        alerts_columns = await self._get_table_columns("alerts")
        if "suppressed" not in alerts_columns:
            return False

        sets = ["suppressed = TRUE", "suppressed_reason = :reason"]
        params: dict[str, Any] = {"id": alert_id, "reason": reason}
        if rag_decision is not None and "rag_decision" in alerts_columns:
            sets.append("rag_decision = :rag")
            params["rag"] = rag_decision
        if vlm_decision is not None and "vlm_decision" in alerts_columns:
            sets.append("vlm_decision = :vlm")
            params["vlm"] = vlm_decision

        query = text(f"""
            UPDATE alerts
            SET {", ".join(sets)}
            WHERE id = :id
        """)
        result = await self.db.execute(query, params)
        await self.db.commit()
        return result.rowcount > 0

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

    async def mark_alert_reviewed(
        self,
        alert_id: int,
        *,
        organization_id: int | None = None,
    ) -> bool:
        """T02-22 defense-in-depth: caller passes the verified
        organization_id (from require_alert_access) so the UPDATE
        cannot cross a tenant boundary even if a future handler
        forgets the dependency. `None` preserves legacy super-admin
        paths that already run under a SuperAdmin gate.
        """
        clause, extra = self._tenant_clause(organization_id)
        query = text(
            f"UPDATE alerts SET reviewed = TRUE WHERE id = :id{clause}"
        )
        result = await self.db.execute(query, {"id": alert_id, **extra})
        await self.db.commit()
        return result.rowcount > 0

    async def delete_alert(
        self,
        alert_id: int,
        *,
        organization_id: int | None = None,
    ) -> bool:
        clause, extra = self._tenant_clause(organization_id)
        query = text(f"DELETE FROM alerts WHERE id = :id{clause}")
        result = await self.db.execute(query, {"id": alert_id, **extra})
        await self.db.commit()
        return result.rowcount > 0

    async def update_feedback_status(
        self,
        alert_id: int,
        status: str,
        *,
        organization_id: int | None = None,
    ) -> bool:
        alerts_columns = await self._get_table_columns("alerts")
        clause, extra = self._tenant_clause(organization_id)

        if "feedback_status" in alerts_columns:
            query = text(f"""
                UPDATE alerts
                SET feedback_status = :status, reviewed = TRUE
                WHERE id = :id{clause}
            """)
            params: dict[str, Any] = {"status": status, "id": alert_id, **extra}
        else:
            query = text(
                f"UPDATE alerts SET reviewed = TRUE WHERE id = :id{clause}"
            )
            params = {"id": alert_id, **extra}

        result = await self.db.execute(query, params)
        await self.db.commit()
        return result.rowcount > 0

    @staticmethod
    def _tenant_clause(
        organization_id: int | None,
    ) -> tuple[str, dict[str, Any]]:
        """Build a WHERE-fragment that pins the row to the caller's org.

        Alerts sometimes carry a NULL `organization_id` column on legacy
        rows; fall back to the camera's organization_id through a
        correlated subquery so the filter still matches after the
        T02-21 handler guard approved the call.
        """
        if organization_id is None:
            return "", {}
        clause = (
            " AND ("
            "  alerts.organization_id = :org_id"
            "  OR (alerts.organization_id IS NULL AND EXISTS ("
            "    SELECT 1 FROM cameras c"
            "    WHERE c.id = alerts.camera_id"
            "      AND c.organization_id = :org_id"
            "  ))"
            ")"
        )
        return clause, {"org_id": organization_id}
