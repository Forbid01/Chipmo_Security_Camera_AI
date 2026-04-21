import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AlertState(StrEnum):
    IDLE = "idle"
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class AlertDecision:
    should_alert: bool
    state: AlertState
    reason: str
    cooldown_until: datetime | None = None


@dataclass
class _TrackAlertState:
    state: AlertState
    last_alert_at: datetime | None = None
    cooldown_until: datetime | None = None


class AlertManager:
    """Deduplicates alerts per camera/track and restores cooldown from DB."""

    def __init__(self):
        self._states: dict[tuple[int | None, int], _TrackAlertState] = {}
        self._lock = Lock()

    async def should_send_alert(
        self,
        db: AsyncSession,
        *,
        camera_id: int | None,
        person_track_id: int,
        cooldown_seconds: int,
        now: datetime | None = None,
    ) -> AlertDecision:
        now = self._normalize_now(now)
        cooldown = max(0, int(cooldown_seconds or 0))
        key = (camera_id, person_track_id)

        with self._lock:
            memory_decision = self._memory_cooldown_decision(key, now)
        if memory_decision:
            return memory_decision

        state_row = await self._get_persisted_state(
            db,
            camera_id=camera_id,
            person_track_id=person_track_id,
        )
        state_decision = self._state_row_decision(state_row, now)
        if state_decision:
            with self._lock:
                self._states[key] = _TrackAlertState(
                    state=state_decision.state,
                    last_alert_at=state_row.get("last_alert_at") if state_row else None,
                    cooldown_until=state_decision.cooldown_until,
                )
            return state_decision

        persisted_alert_at = await self._get_latest_alert_at(
            db,
            camera_id=camera_id,
            person_track_id=person_track_id,
        )

        with self._lock:
            memory_decision = self._memory_cooldown_decision(key, now)
            if memory_decision:
                return memory_decision

            persisted_decision = None
            persisted_cooldown_until = None
            if persisted_alert_at is not None:
                persisted_alert_at = self._normalize_datetime(persisted_alert_at, now)
                cooldown_until = persisted_alert_at + timedelta(seconds=cooldown)
                if now < cooldown_until:
                    self._states[key] = _TrackAlertState(
                        state=AlertState.COOLDOWN,
                        last_alert_at=persisted_alert_at,
                        cooldown_until=cooldown_until,
                    )
                    persisted_cooldown_until = cooldown_until
                    persisted_decision = AlertDecision(
                        should_alert=False,
                        state=AlertState.COOLDOWN,
                        reason="persisted_cooldown",
                        cooldown_until=cooldown_until,
                    )

            if persisted_decision:
                decision = persisted_decision
            else:
                cooldown_until = now + timedelta(seconds=cooldown)
                self._states[key] = _TrackAlertState(
                    state=AlertState.ACTIVE,
                    last_alert_at=now,
                    cooldown_until=cooldown_until,
                )
                decision = AlertDecision(
                    should_alert=True,
                    state=AlertState.ACTIVE,
                    reason="new_alert",
                    cooldown_until=cooldown_until,
                )

        if persisted_decision:
            await self._mark_cooldown(
                db,
                camera_id=camera_id,
                person_track_id=person_track_id,
                alert_id=None,
                last_alert_at=persisted_alert_at,
                cooldown_until=persisted_cooldown_until,
            )
            return decision

        await self._mark_active(
            db,
            camera_id=camera_id,
            person_track_id=person_track_id,
            now=now,
            cooldown_until=cooldown_until,
        )
        return decision

    async def record_alert_committed(
        self,
        db: AsyncSession,
        *,
        camera_id: int | None,
        person_track_id: int,
        alert_id: int | None,
        cooldown_until: datetime | None,
        now: datetime | None = None,
    ) -> None:
        now = self._normalize_now(now)
        cooldown_until = self._normalize_now(cooldown_until)
        key = (camera_id, person_track_id)
        with self._lock:
            self._states[key] = _TrackAlertState(
                state=AlertState.COOLDOWN,
                last_alert_at=now,
                cooldown_until=cooldown_until,
            )
        await self._mark_cooldown(
            db,
            camera_id=camera_id,
            person_track_id=person_track_id,
            alert_id=alert_id,
            last_alert_at=now,
            cooldown_until=cooldown_until,
        )

    async def mark_resolved(
        self,
        db: AsyncSession,
        *,
        camera_id: int | None,
        person_track_id: int,
        resolved_at: datetime | None = None,
    ) -> None:
        resolved_at = self._normalize_now(resolved_at)
        key = (camera_id, person_track_id)
        with self._lock:
            self._states[key] = _TrackAlertState(state=AlertState.RESOLVED)
        await self._mark_resolved(
            db,
            camera_id=camera_id,
            person_track_id=person_track_id,
            resolved_at=resolved_at,
        )

    def _memory_cooldown_decision(
        self,
        key: tuple[int | None, int],
        now: datetime,
    ) -> AlertDecision | None:
        state = self._states.get(key)
        if state and state.cooldown_until and now < state.cooldown_until:
            return AlertDecision(
                should_alert=False,
                state=state.state,
                reason=f"memory_{state.state.value}",
                cooldown_until=state.cooldown_until,
            )
        return None

    def _state_row_decision(
        self,
        state_row: dict[str, Any] | None,
        now: datetime,
    ) -> AlertDecision | None:
        if not state_row:
            return None
        state = AlertState(state_row["state"])
        cooldown_until = state_row.get("cooldown_until")
        if cooldown_until is None or state not in {AlertState.ACTIVE, AlertState.COOLDOWN}:
            return None
        cooldown_until = self._normalize_datetime(cooldown_until, now)
        if now >= cooldown_until:
            return None
        return AlertDecision(
            should_alert=False,
            state=state,
            reason=f"state_table_{state.value}",
            cooldown_until=cooldown_until,
        )

    async def _get_persisted_state(
        self,
        db: AsyncSession,
        *,
        camera_id: int | None,
        person_track_id: int,
    ) -> dict[str, Any] | None:
        from app.db.repository.alert_state import AlertStateRepository

        try:
            return await AlertStateRepository(db).get_state(
                camera_id=camera_id,
                person_track_id=person_track_id,
            )
        except Exception as exc:
            logger.warning("Alert state lookup failed: %s", exc)
            return None

    async def _mark_active(
        self,
        db: AsyncSession,
        *,
        camera_id: int | None,
        person_track_id: int,
        now: datetime,
        cooldown_until: datetime,
    ) -> None:
        from app.db.repository.alert_state import AlertStateRepository

        try:
            await AlertStateRepository(db).mark_active(
                camera_id=camera_id,
                person_track_id=person_track_id,
                now=now,
                cooldown_until=cooldown_until,
            )
        except Exception as exc:
            logger.warning("Alert state active update failed: %s", exc)

    async def _mark_cooldown(
        self,
        db: AsyncSession,
        *,
        camera_id: int | None,
        person_track_id: int,
        alert_id: int | None,
        last_alert_at: datetime,
        cooldown_until: datetime,
    ) -> None:
        from app.db.repository.alert_state import AlertStateRepository

        try:
            await AlertStateRepository(db).mark_cooldown(
                camera_id=camera_id,
                person_track_id=person_track_id,
                alert_id=alert_id,
                last_alert_at=last_alert_at,
                cooldown_until=cooldown_until,
            )
        except Exception as exc:
            logger.warning("Alert state cooldown update failed: %s", exc)

    async def _mark_resolved(
        self,
        db: AsyncSession,
        *,
        camera_id: int | None,
        person_track_id: int,
        resolved_at: datetime,
    ) -> None:
        from app.db.repository.alert_state import AlertStateRepository

        try:
            await AlertStateRepository(db).mark_resolved(
                camera_id=camera_id,
                person_track_id=person_track_id,
                resolved_at=resolved_at,
            )
        except Exception as exc:
            logger.warning("Alert state resolved update failed: %s", exc)

    async def _get_latest_alert_at(
        self,
        db: AsyncSession,
        *,
        camera_id: int | None,
        person_track_id: int,
    ) -> datetime | None:
        params: dict[str, Any] = {"person_track_id": person_track_id}
        conditions = ["person_id = :person_track_id"]
        if camera_id is not None:
            conditions.append("camera_id = :camera_id")
            params["camera_id"] = camera_id

        query = text(f"""
            SELECT event_time
            FROM alerts
            WHERE {" AND ".join(conditions)}
            ORDER BY event_time DESC
            LIMIT 1
        """)
        try:
            result = await db.execute(query, params)
        except Exception as exc:
            logger.warning("Alert cooldown DB lookup failed: %s", exc)
            return None

        row = result.fetchone()
        return self._row_event_time(row)

    @staticmethod
    def _row_event_time(row: Any) -> datetime | None:
        if row is None:
            return None
        if hasattr(row, "_mapping") and "event_time" in row._mapping:
            return row._mapping["event_time"]
        return row[0]

    @staticmethod
    def _normalize_now(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @staticmethod
    def _normalize_datetime(value: datetime, reference: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=reference.tzinfo)
        return value


alert_manager = AlertManager()
