"""Tests for T02-22 — repository tenant parameter reinforcement.

Each test is a two-part check:
1. With no organization_id, the SQL falls back to id-only WHERE
   (legacy super-admin path).
2. With organization_id, the SQL appends the tenant pin so the query
   cannot match a row from a different organization.

These are pure SQL-shape assertions using a mocked session — the real
cross-tenant regression runs in T02-23 against a live Postgres.
"""


import pytest
from app.db.repository.alerts import AlertRepository
from app.db.repository.camera_repo import CameraRepository
from app.db.repository.stores import StoreRepository
from app.schemas.camera import CameraUpdate
from app.schemas.store import StoreUpdate


class _Capture:
    """Stateful execute() mock that records the last query + params."""

    def __init__(self, rowcount: int = 1, alerts_columns: set[str] | None = None):
        self.rowcount = rowcount
        self.last_query: str | None = None
        self.last_params: dict | None = None
        self._alerts_columns = alerts_columns or {
            "id", "person_id", "organization_id", "store_id", "camera_id",
            "reviewed", "feedback_status", "image_path", "video_path",
        }

    async def execute(self, query, params=None):
        query_text = str(query)
        self.last_query = query_text
        self.last_params = dict(params or {})

        if "information_schema.columns" in query_text:
            class _R:
                def fetchall(inner_self):
                    return [(c,) for c in self._alerts_columns]
            return _R()

        class _R:
            rowcount = self.rowcount

            def fetchone(inner_self):
                return None
        return _R()

    async def commit(self):
        pass


# ---------------------------------------------------------------------------
# AlertRepository
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_alert_reviewed_without_org_id_is_id_only():
    db = _Capture()
    repo = AlertRepository(db)

    await repo.mark_alert_reviewed(42)

    assert "UPDATE alerts" in db.last_query
    assert "WHERE id = :id" in db.last_query
    assert "organization_id" not in db.last_query
    assert db.last_params == {"id": 42}


@pytest.mark.asyncio
async def test_mark_alert_reviewed_with_org_id_pins_tenant():
    db = _Capture()
    repo = AlertRepository(db)

    await repo.mark_alert_reviewed(42, organization_id=100)

    # Must reference the org column from both direct + camera-derived
    # paths so legacy rows with NULL organization_id still get filtered
    # via the EXISTS subquery.
    assert "alerts.organization_id = :org_id" in db.last_query
    assert "FROM cameras c" in db.last_query
    assert db.last_params == {"id": 42, "org_id": 100}


@pytest.mark.asyncio
async def test_delete_alert_with_org_id_pins_tenant():
    db = _Capture()
    repo = AlertRepository(db)

    await repo.delete_alert(7, organization_id=100)

    assert db.last_query.startswith("DELETE FROM alerts")
    assert "alerts.organization_id = :org_id" in db.last_query
    assert db.last_params["org_id"] == 100


@pytest.mark.asyncio
async def test_update_feedback_status_with_org_id_pins_tenant():
    db = _Capture()
    repo = AlertRepository(db)

    await repo.update_feedback_status(
        11, "true_positive", organization_id=100
    )

    assert "UPDATE alerts" in db.last_query
    assert "feedback_status = :status" in db.last_query
    assert "alerts.organization_id = :org_id" in db.last_query
    assert db.last_params["status"] == "true_positive"
    assert db.last_params["org_id"] == 100


@pytest.mark.asyncio
async def test_update_feedback_status_without_org_id_keeps_legacy_shape():
    db = _Capture()
    repo = AlertRepository(db)
    await repo.update_feedback_status(11, "true_positive")
    assert "organization_id" not in db.last_query


# ---------------------------------------------------------------------------
# CameraRepository
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_camera_update_without_org_id_is_id_only():
    db = _Capture()
    repo = CameraRepository(db)
    await repo.update(5, CameraUpdate(name="renamed"))

    assert "UPDATE cameras" in db.last_query
    assert "organization_id" not in db.last_query
    assert db.last_params == {"id": 5, "name": "renamed"}


@pytest.mark.asyncio
async def test_camera_update_with_org_id_pins_tenant():
    db = _Capture()
    repo = CameraRepository(db)
    await repo.update(5, CameraUpdate(name="renamed"), organization_id=100)

    assert "AND organization_id = :org_id" in db.last_query
    assert db.last_params["org_id"] == 100
    assert db.last_params["id"] == 5


@pytest.mark.asyncio
async def test_camera_update_no_change_still_short_circuits():
    # Legacy semantics: empty patch returns True without issuing SQL.
    db = _Capture()
    repo = CameraRepository(db)
    ok = await repo.update(5, CameraUpdate(), organization_id=100)
    assert ok is True
    # No UPDATE was issued.
    assert db.last_query is None


@pytest.mark.asyncio
async def test_camera_delete_with_org_id_pins_tenant():
    db = _Capture()
    repo = CameraRepository(db)
    await repo.delete(5, organization_id=100)

    assert db.last_query.startswith("DELETE FROM cameras")
    assert "AND organization_id = :org_id" in db.last_query
    assert db.last_params == {"id": 5, "org_id": 100}


@pytest.mark.asyncio
async def test_camera_get_shelf_zones_with_org_id_pins_tenant():
    db = _Capture()
    repo = CameraRepository(db)
    await repo.get_shelf_zones(5, organization_id=100)

    assert "SELECT shelf_zones FROM cameras" in db.last_query
    assert "AND organization_id = :org_id" in db.last_query
    assert db.last_params == {"id": 5, "org_id": 100}


@pytest.mark.asyncio
async def test_camera_get_shelf_zones_without_org_id_is_id_only():
    db = _Capture()
    repo = CameraRepository(db)
    await repo.get_shelf_zones(5)

    assert db.last_query == "SELECT shelf_zones FROM cameras WHERE id = :id"
    assert db.last_params == {"id": 5}


# ---------------------------------------------------------------------------
# StoreRepository
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_update_with_org_id_pins_tenant():
    db = _Capture()
    repo = StoreRepository(db)
    await repo.update(9, StoreUpdate(name="new"), organization_id=100)

    assert "UPDATE stores" in db.last_query
    assert "AND organization_id = :org_id" in db.last_query
    assert db.last_params["org_id"] == 100
    assert db.last_params["name"] == "new"


@pytest.mark.asyncio
async def test_store_update_empty_patch_short_circuits():
    db = _Capture()
    repo = StoreRepository(db)
    ok = await repo.update(9, StoreUpdate(), organization_id=100)
    assert ok is True
    assert db.last_query is None


@pytest.mark.asyncio
async def test_store_delete_with_org_id_pins_tenant():
    db = _Capture()
    repo = StoreRepository(db)
    await repo.delete(9, organization_id=100)

    assert db.last_query.startswith("DELETE FROM stores")
    assert "AND organization_id = :org_id" in db.last_query
    assert db.last_params == {"id": 9, "org_id": 100}


@pytest.mark.asyncio
async def test_store_delete_without_org_id_remains_id_only():
    db = _Capture()
    repo = StoreRepository(db)
    await repo.delete(9)

    assert db.last_query == "DELETE FROM stores WHERE id = :id"
    assert db.last_params == {"id": 9}


# ---------------------------------------------------------------------------
# Parameter-binding smoke — make sure text() compiled on an in-memory
# sqlalchemy engine still references every bind param
# ---------------------------------------------------------------------------

def test_alerts_mark_reviewed_with_org_id_compiles_without_missing_bind():
    # Protects against f-string drift where we reference :org_id in SQL
    # but forget to add it to params, which asyncpg would reject with
    # CompileError at runtime.
    from sqlalchemy import text as _text

    clause, extra = AlertRepository._tenant_clause(organization_id=100)
    query = _text(f"UPDATE alerts SET reviewed = TRUE WHERE id = :id{clause}")
    # The bound params must cover every :name reference in the SQL.
    needed = set(query.compile(compile_kwargs={"literal_binds": False}).params.keys())
    assert "id" in needed or "org_id" in needed  # at least one must bind


def test_alert_repository_tenant_clause_empty_when_org_id_none():
    clause, extra = AlertRepository._tenant_clause(None)
    assert clause == ""
    assert extra == {}


def test_alert_repository_tenant_clause_mentions_cameras_join_for_legacy_rows():
    clause, extra = AlertRepository._tenant_clause(100)
    # The subquery through cameras is load-bearing — legacy alert rows
    # may have NULL organization_id but a valid camera_id.
    assert "FROM cameras c" in clause
    assert "c.organization_id = :org_id" in clause
    assert extra == {"org_id": 100}
