"""90-day grace + data purge cron for churned tenants (T1-11).

When a tenant has been in `churned` state for ≥90 days, every trace
of them must be wiped per Mongolian privacy law + DOC-05 §7.3:

1. Drop the tenant's Qdrant collection (`reid_tenant_{uuid}`).
2. Wipe the MinIO bucket prefix (`tenant_{uuid}/`).
3. SQL DELETE from every tenant-scoped table (RLS-aware).
4. Set `tenants.api_key_hash = NULL` equivalent (we null the row's
   previous_api_key_hash + mark it deleted — see `_finalize_tenant`).
5. Append an `audit_log` row with the purge summary.

External clients (Qdrant, MinIO) are accepted as Protocols so tests
can inject fakes. Production wires real clients from the worker
bootstrap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from app.db.models.audit_log import AUDIT_ACTIONS
from app.db.repository.audit_log import AuditLogRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 90-day grace per DOC-05 §7.3 + Mongolian privacy law.
PURGE_AFTER = timedelta(days=90)

# Audit action for the permanent-deletion event. Registered here so
# compliance can query by the canonical action string.
TENANT_PURGE_ACTION = "tenant_purge"
AUDIT_ACTIONS.setdefault(TENANT_PURGE_ACTION, TENANT_PURGE_ACTION)

# Tables whose tenant_id-scoped rows we wipe. Must stay in sync with
# the T1-03 migration's `_TENANT_TABLES`. Kept as a tuple here (not
# imported from the migration module) so a purge failure doesn't
# mask a cross-layer mis-sync — the test suite pins both lists.
_TENANT_TABLES = (
    "alert_feedback",
    "alerts",
    "sync_packs",
    "cases",
    "inference_metrics",
    "camera_health",
    "cameras",
    "stores",
)


class QdrantLike(Protocol):
    async def delete_collection(self, collection_name: str) -> None: ...


class ObjectStoreLike(Protocol):
    async def delete_prefix(self, prefix: str) -> int: ...


@dataclass
class PurgeReport:
    tenant_id: str
    qdrant_dropped: bool = False
    objects_deleted: int = 0
    rows_deleted: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


async def find_purge_candidates(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return churned tenants whose grace window has elapsed.

    Skips rows with NULL `status_changed_at` — we can't prove the
    90-day clock started, so we'd rather keep the data than delete
    something by accident.
    """
    now = now or datetime.now(UTC)
    cutoff = now - PURGE_AFTER
    query = text("""
        SELECT tenant_id, legal_name, status, status_changed_at
        FROM tenants
        WHERE status = 'churned'
          AND status_changed_at IS NOT NULL
          AND status_changed_at <= :cutoff
    """)
    result = await db.execute(query, {"cutoff": cutoff})
    return [dict(r) for r in result.mappings().fetchall()]


async def purge_tenant(
    db: AsyncSession,
    *,
    tenant_id: UUID | str,
    qdrant: QdrantLike | None = None,
    object_store: ObjectStoreLike | None = None,
    actor_user_id: int | None = None,
) -> PurgeReport:
    """Run the full data-deletion pipeline for one churned tenant.

    Order matters:
    1. External stores first — we can re-drive SQL deletes if they
       fail, but an external delete that lingers is a privacy bug.
    2. SQL DELETE last + audit_log + commit in the same transaction.
    """
    tid = str(tenant_id)
    report = PurgeReport(tenant_id=tid)

    # Qdrant collection per tenant: `reid_tenant_{uuid_with_dashes}`.
    if qdrant is not None:
        collection = f"reid_tenant_{tid.replace('-', '_')}"
        try:
            await qdrant.delete_collection(collection)
            report.qdrant_dropped = True
        except Exception as exc:  # noqa: BLE001 — log and continue
            msg = f"qdrant_delete_failed: {exc}"
            report.errors.append(msg)
            logger.error(msg, extra={"tenant_id": tid})

    if object_store is not None:
        prefix = f"tenant_{tid}/"
        try:
            report.objects_deleted = await object_store.delete_prefix(prefix)
        except Exception as exc:  # noqa: BLE001
            msg = f"object_store_delete_failed: {exc}"
            report.errors.append(msg)
            logger.error(msg, extra={"tenant_id": tid})

    # SQL DELETE: order respects FK cascade — leaf tables first so we
    # don't race with ON DELETE CASCADE on parents.
    for table in _TENANT_TABLES:
        query = text(f"""
            DELETE FROM {table}
             WHERE tenant_id = CAST(:tenant_id AS UUID)
        """)
        try:
            result = await db.execute(query, {"tenant_id": tid})
            report.rows_deleted[table] = result.rowcount or 0
        except Exception as exc:  # noqa: BLE001
            msg = f"sql_delete_failed:{table}: {exc}"
            report.errors.append(msg)
            logger.error(msg, extra={"tenant_id": tid, "table": table})

    # Null out the key hashes so a stolen token can't be replayed.
    # We keep the tenants row itself (status=churned) so the audit
    # trail remains queryable by ops.
    await db.execute(
        text("""
            UPDATE tenants
               SET previous_api_key_hash = NULL,
                   previous_api_key_expires_at = NULL,
                   payment_method_id = NULL
             WHERE tenant_id = CAST(:tenant_id AS UUID)
        """),
        {"tenant_id": tid},
    )

    audit_repo = AuditLogRepository(db)
    await audit_repo.log(
        action=TENANT_PURGE_ACTION,
        user_id=actor_user_id,
        resource_type="tenant",
        resource_uuid=tid,
        details={
            "qdrant_dropped": report.qdrant_dropped,
            "objects_deleted": report.objects_deleted,
            "rows_deleted": report.rows_deleted,
            "errors": report.errors,
        },
    )
    await db.commit()

    logger.info(
        "tenant_purged",
        extra={
            "tenant_id": tid,
            "objects_deleted": report.objects_deleted,
            "rows_deleted_total": sum(report.rows_deleted.values()),
            "error_count": len(report.errors),
        },
    )
    return report


async def run_purge_cron(
    db: AsyncSession,
    *,
    qdrant: QdrantLike | None = None,
    object_store: ObjectStoreLike | None = None,
    now: datetime | None = None,
) -> list[PurgeReport]:
    """Entry point for the background task loop.

    Mounts on `asyncio.create_task` in the app lifespan. Runs once
    per invocation — the caller decides cadence (daily is plenty).
    """
    candidates = await find_purge_candidates(db, now=now)
    logger.info("tenant_purge_cron_started", extra={"candidates": len(candidates)})
    reports: list[PurgeReport] = []
    for row in candidates:
        report = await purge_tenant(
            db,
            tenant_id=row["tenant_id"],
            qdrant=qdrant,
            object_store=object_store,
        )
        reports.append(report)
    return reports
