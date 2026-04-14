import logging
import json
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


class FeedbackRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_feedback(self, alert_id: int, feedback_type: str,
                              reviewer_id: int = None, notes: str = None) -> Optional[int]:
        # Get alert details for learning data
        alert_q = text("SELECT * FROM alerts WHERE id = :id")
        alert_result = await self.db.execute(alert_q, {"id": alert_id})
        alert = alert_result.mappings().fetchone()
        if not alert:
            return None

        store_id = alert.get("store_id") if alert else None
        score = alert.get("confidence_score") if alert else None

        query = text("""
            INSERT INTO alert_feedback (alert_id, store_id, feedback_type, reviewer_id, notes, score_at_alert)
            VALUES (:alert_id, :store_id, :fb_type, :reviewer_id, :notes, :score)
            ON CONFLICT (alert_id) DO UPDATE SET
                feedback_type = :fb_type, reviewer_id = :reviewer_id, notes = :notes
            RETURNING id
        """)
        result = await self.db.execute(query, {
            "alert_id": alert_id, "store_id": store_id,
            "fb_type": feedback_type, "reviewer_id": reviewer_id,
            "notes": notes, "score": score,
        })

        # Update alert feedback_status
        await self.db.execute(
            text("UPDATE alerts SET feedback_status = :status, reviewed = TRUE WHERE id = :id"),
            {"status": feedback_type, "id": alert_id}
        )

        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def get_stats(self, store_id: int = None) -> Dict[str, Any]:
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

        # Count unreviewed alerts
        unreviewed_q = text("SELECT COUNT(*) FROM alerts WHERE feedback_status = 'unreviewed'")
        unreviewed_result = await self.db.execute(unreviewed_q)
        unreviewed = unreviewed_result.scalar() or 0

        return {
            "total_feedback": total,
            "true_positives": tp,
            "false_positives": fp,
            "unreviewed": unreviewed,
            "precision": round(precision, 3) if precision else None,
        }

    async def get_learning_status(self, store_id: int = None) -> Dict[str, Any]:
        """Auto-learning системийн одоогийн төлөв."""
        stats = await self.get_stats(store_id)

        # Get current threshold for store
        threshold = 80.0
        if store_id:
            q = text("SELECT alert_threshold FROM stores WHERE id = :id")
            result = await self.db.execute(q, {"id": store_id})
            row = result.fetchone()
            if row:
                threshold = row[0]

        # Get learned adjustments
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

    async def get_feedback_for_learning(self, store_id: int = None,
                                        limit: int = 1000) -> list:
        """Auto-learning-д ашиглах feedback өгөгдөл."""
        conditions = ""
        params = {"limit": limit}
        if store_id:
            conditions = "AND af.store_id = :store_id"
            params["store_id"] = store_id

        query = text(f"""
            SELECT af.*, a.confidence_score, a.description
            FROM alert_feedback af
            JOIN alerts a ON af.alert_id = a.id
            WHERE af.feedback_type IN ('true_positive', 'false_positive')
            {conditions}
            ORDER BY af.created_at DESC
            LIMIT :limit
        """)
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().fetchall()]
