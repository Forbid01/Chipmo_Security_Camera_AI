"""Auto-learning system - feedback-ээс суралцаж, дэлгүүр бүрт тохирсон тохиргоо хийнэ.

Ажиллах зарчим:
1. Ажилтнууд alert-д true_positive/false_positive гэж тэмдэглэнэ
2. Систем 20+ feedback цугларсны дараа суралцаж эхэлнэ
3. Дэлгүүр бүрт тохирсон threshold, score weights тооцоолно
4. Шинэ тохиргоог model_versions хүснэгтэд хадгална
5. AI service шинэ тохиргоог автоматаар ашиглана
"""

import json
import logging
import asyncio
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Default score weights
DEFAULT_WEIGHTS = {
    "looking_around": 1.5,
    "item_pickup": 15.0,
    "body_block": 3.0,
    "crouch": 1.0,
    "wrist_to_torso": 5.0,
    "rapid_movement": 1.5,
}


class AutoLearner:
    """Feedback-ээс суралцаж, threshold болон score weights-г тохируулна."""

    def __init__(self):
        self._store_configs: Dict[int, dict] = {}
        self._learning_lock = asyncio.Lock()

    def get_store_config(self, store_id: int) -> dict:
        """Дэлгүүрийн одоогийн AI тохиргоог авах."""
        return self._store_configs.get(store_id, {
            "threshold": 80.0,
            "weights": DEFAULT_WEIGHTS.copy(),
        })

    async def learn_from_feedback(self, db_session) -> Dict[int, dict]:
        """Бүх дэлгүүрийн feedback-ээс суралцах."""
        async with self._learning_lock:
            from app.db.repository.feedback_repo import FeedbackRepository
            repo = FeedbackRepository(db_session)

            # Get all stores with feedback
            from sqlalchemy import text
            stores_q = text("""
                SELECT DISTINCT store_id FROM alert_feedback
                WHERE store_id IS NOT NULL AND feedback_type IN ('true_positive', 'false_positive')
            """)
            result = await db_session.execute(stores_q)
            store_ids = [row[0] for row in result.fetchall()]

            updated = {}
            for store_id in store_ids:
                config = await self._learn_for_store(db_session, repo, store_id)
                if config:
                    self._store_configs[store_id] = config
                    updated[store_id] = config

            return updated

    async def _learn_for_store(self, db_session, repo, store_id: int) -> Optional[dict]:
        """Нэг дэлгүүрийн feedback-ээс суралцах."""
        feedback_data = await repo.get_feedback_for_learning(store_id=store_id)

        if len(feedback_data) < 20:
            logger.info(f"Store {store_id}: Not enough feedback ({len(feedback_data)}/20)")
            return None

        tp_scores = []
        fp_scores = []

        for fb in feedback_data:
            score = fb.get("confidence_score") or fb.get("score_at_alert")
            if score is None:
                continue
            if fb["feedback_type"] == "true_positive":
                tp_scores.append(score)
            elif fb["feedback_type"] == "false_positive":
                fp_scores.append(score)

        if not tp_scores and not fp_scores:
            return None

        # Calculate optimal threshold
        new_threshold = self._calculate_optimal_threshold(tp_scores, fp_scores)

        # Calculate adjusted weights based on behavior patterns
        new_weights = await self._adjust_weights(db_session, store_id, feedback_data)

        config = {
            "threshold": new_threshold,
            "weights": new_weights,
        }

        # Save to model_versions
        await self._save_model_version(db_session, store_id, config, len(feedback_data))

        # Update store threshold
        from sqlalchemy import text
        await db_session.execute(
            text("UPDATE stores SET alert_threshold = :threshold WHERE id = :id"),
            {"threshold": new_threshold, "id": store_id}
        )
        await db_session.commit()

        logger.info(
            f"Store {store_id}: Learned threshold={new_threshold:.1f} "
            f"from {len(feedback_data)} feedback items "
            f"(TP: {len(tp_scores)}, FP: {len(fp_scores)})"
        )

        return config

    def _calculate_optimal_threshold(self, tp_scores: list, fp_scores: list) -> float:
        """True/false positive score-уудаас оновчтой threshold тооцоолох.

        Зорилго: False positive-г бууруулж, true positive-г алдахгүй байх.
        """
        if not tp_scores and not fp_scores:
            return 80.0

        # If we have both TP and FP, find the boundary
        if tp_scores and fp_scores:
            avg_tp = sum(tp_scores) / len(tp_scores)
            avg_fp = sum(fp_scores) / len(fp_scores)

            # Threshold should be between avg FP and avg TP
            # Weighted toward reducing false positives (60% toward FP avg)
            if avg_tp > avg_fp:
                threshold = avg_fp * 0.4 + avg_tp * 0.6
            else:
                # If FP scores are higher than TP, raise threshold
                threshold = max(avg_tp, avg_fp) * 1.1

            # Clamp to reasonable range
            return max(40.0, min(150.0, round(threshold, 1)))

        # Only TPs - lower threshold slightly to catch more
        if tp_scores:
            min_tp = min(tp_scores)
            return max(40.0, round(min_tp * 0.85, 1))

        # Only FPs - raise threshold to reduce false alarms
        if fp_scores:
            max_fp = max(fp_scores)
            return min(150.0, round(max_fp * 1.3, 1))

        return 80.0

    async def _adjust_weights(self, db_session, store_id: int, feedback_data: list) -> dict:
        """Behavior pattern-ээс score weight-г тохируулах."""
        weights = DEFAULT_WEIGHTS.copy()

        # Count which behaviors lead to FP vs TP
        behavior_tp_count = {}
        behavior_fp_count = {}

        for fb in feedback_data:
            desc = fb.get("description") or ""
            behaviors = self._extract_behaviors(desc)
            counter = behavior_tp_count if fb["feedback_type"] == "true_positive" else behavior_fp_count
            for b in behaviors:
                counter[b] = counter.get(b, 0) + 1

        # Adjust weights: increase for TP-associated behaviors, decrease for FP-associated
        for behavior, default_weight in DEFAULT_WEIGHTS.items():
            tp_count = behavior_tp_count.get(behavior, 0)
            fp_count = behavior_fp_count.get(behavior, 0)
            total = tp_count + fp_count

            if total >= 5:  # Need enough data points
                tp_ratio = tp_count / total
                # Scale weight: if mostly TP, increase; if mostly FP, decrease
                adjustment = 0.5 + tp_ratio  # Range: 0.5 to 1.5
                weights[behavior] = round(default_weight * adjustment, 2)

        return weights

    def _extract_behaviors(self, description: str) -> list:
        """Alert description-ээс behavior-уудыг задлах."""
        behavior_map = {
            "Орчноо харах": "looking_around",
            "авах": "item_pickup",
            "Биеэр далдлах": "body_block",
            "Бөхийх": "crouch",
            "нуух": "wrist_to_torso",
            "Хурдан хөдөлгөөн": "rapid_movement",
        }
        found = []
        for keyword, behavior in behavior_map.items():
            if keyword in description:
                found.append(behavior)
        return found

    async def _save_model_version(self, db_session, store_id: int, config: dict,
                                  feedback_count: int):
        from sqlalchemy import text

        # Deactivate previous versions
        await db_session.execute(
            text("UPDATE model_versions SET is_active = FALSE WHERE store_id = :sid"),
            {"sid": store_id}
        )

        # Save new version
        version = datetime.now(timezone.utc).strftime("v%Y%m%d_%H%M%S")
        await db_session.execute(
            text("""
                INSERT INTO model_versions (store_id, version, model_type,
                    learned_threshold, learned_score_weights, total_feedback_used, is_active)
                VALUES (:sid, :ver, 'behavior_scoring', :threshold, :weights, :count, TRUE)
            """),
            {
                "sid": store_id, "ver": version,
                "threshold": config["threshold"],
                "weights": json.dumps(config["weights"]),
                "count": feedback_count,
            }
        )
        await db_session.commit()


# Global singleton
auto_learner = AutoLearner()
