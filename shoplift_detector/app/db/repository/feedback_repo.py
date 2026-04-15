import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class FeedbackRepository:
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

    async def _get_alert_feedback_context(self, alert_id: int) -> dict[str, Any] | None:
        alerts_columns = await self._get_table_columns("alerts")
        cameras_columns = await self._get_table_columns("cameras")
        has_alert_store_id = "store_id" in alerts_columns
        has_alert_camera_id = "camera_id" in alerts_columns
        has_camera_store_id = "store_id" in cameras_columns
        join_camera = has_alert_camera_id and has_camera_store_id

        store_select = "a.store_id AS store_id" if has_alert_store_id else (
            "c.store_id AS store_id" if join_camera else "NULL::integer AS store_id"
        )
        score_select = (
            "a.confidence_score AS confidence_score"
            if "confidence_score" in alerts_columns
            else "NULL::double precision AS confidence_score"
        )
        camera_join = "LEFT JOIN cameras c ON a.camera_id = c.id" if join_camera else ""

        query = text(f"""
            SELECT
                {store_select},
                {score_select}
            FROM alerts a
            {camera_join}
            WHERE a.id = :id
        """)
        result = await self.db.execute(query, {"id": alert_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def create_feedback(
        self,
        alert_id: int,
        feedback_type: str,
        reviewer_id: int = None,
        notes: str = None,
    ) -> int | None:
        alert = await self._get_alert_feedback_context(alert_id)
        if not alert:
            return None

        query = text("""
            INSERT INTO alert_feedback (alert_id, store_id, feedback_type, reviewer_id, notes, score_at_alert)
            VALUES (:alert_id, :store_id, :fb_type, :reviewer_id, :notes, :score)
            ON CONFLICT (alert_id) DO UPDATE SET
                feedback_type = :fb_type, reviewer_id = :reviewer_id, notes = :notes
            RETURNING id
        """)
        result = await self.db.execute(
            query,
            {
                "alert_id": alert_id,
                "store_id": alert.get("store_id"),
                "fb_type": feedback_type,
                "reviewer_id": reviewer_id,
                "notes": notes,
                "score": alert.get("confidence_score"),
            },
        )

        alerts_columns = await self._get_table_columns("alerts")
        if "feedback_status" in alerts_columns:
            await self.db.execute(
                text("UPDATE alerts SET feedback_status = :status, reviewed = TRUE WHERE id = :id"),
                {"status": feedback_type, "id": alert_id},
            )
        else:
            await self.db.execute(
                text("UPDATE alerts SET reviewed = TRUE WHERE id = :id"),
                {"id": alert_id},
            )

        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def get_stats(self, store_id: int = None) -> dict[str, Any]:
        conditions = ""
        params = {}
        if store_id:
            conditions = "WHERE store_id = :store_id"
            params["store_id"] = store_id

        query = text(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN feedback_type = 'true_positive' THEN 1 ELSE 0 END) as true_positives,
                SUM(CASE WHEN feedback_type = 'false_positive' THEN 1 ELSE 0 END) as false_positives
            FROM alert_feedback
            {conditions}
        """)
        result = await self.db.execute(query, params)
        row = result.mappings().fetchone()

        total = row["total"] or 0
        tp = row["true_positives"] or 0
        fp = row["false_positives"] or 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else None

        alerts_columns = await self._get_table_columns("alerts")
        if "feedback_status" in alerts_columns:
            unreviewed_q = text("SELECT COUNT(*) FROM alerts WHERE feedback_status = 'unreviewed'")
        else:
            unreviewed_q = text("SELECT COUNT(*) FROM alerts WHERE COALESCE(reviewed, FALSE) = FALSE")
        unreviewed_result = await self.db.execute(unreviewed_q)
        unreviewed = unreviewed_result.scalar() or 0

        return {
            "total_feedback": total,
            "true_positives": tp,
            "false_positives": fp,
            "unreviewed": unreviewed,
            "precision": round(precision, 3) if precision else None,
        }

    async def get_learning_status(self, store_id: int = None) -> dict[str, Any]:
        stats = await self.get_stats(store_id)

        threshold = 80.0
        if store_id:
            q = text("SELECT alert_threshold FROM stores WHERE id = :id")
            result = await self.db.execute(q, {"id": store_id})
            row = result.fetchone()
            if row:
                threshold = row[0]

        learned_q = text("""
            SELECT learned_threshold, learned_score_weights, total_feedback_used
            FROM model_versions
            WHERE (:store_id IS NULL OR store_id = :store_id) AND is_active = TRUE
            ORDER BY trained_at DESC LIMIT 1
        """)
        learned_result = await self.db.execute(learned_q, {"store_id": store_id})
        learned = learned_result.mappings().fetchone()

        return {
            "store_id": store_id,
            "current_threshold": threshold,
            "learned_threshold": learned["learned_threshold"] if learned else None,
            "total_feedback_used": learned["total_feedback_used"] if learned else 0,
            "feedback_stats": stats,
            "auto_learn_ready": stats["total_feedback"] >= 20,
        }

    async def get_feedback_for_learning(self, store_id: int = None, limit: int = 1000) -> list:
        alerts_columns = await self._get_table_columns("alerts")
        score_select = (
            "a.confidence_score AS confidence_score"
            if "confidence_score" in alerts_columns
            else "af.score_at_alert AS confidence_score"
        )

        conditions = ""
        params = {"limit": limit}
        if store_id:
            conditions = "AND af.store_id = :store_id"
            params["store_id"] = store_id

        query = text(f"""
            SELECT af.*, {score_select}, a.description
            FROM alert_feedback af
            JOIN alerts a ON af.alert_id = a.id
            WHERE af.feedback_type IN ('true_positive', 'false_positive')
            {conditions}
            ORDER BY af.created_at DESC
            LIMIT :limit
        """)
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().fetchall()]
