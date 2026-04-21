from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from shoplift_detector.app.db.repository.cases import CaseRepository


class _MappingResult:
    def __init__(self, mapping=None, rows=None, rowcount=1):
        self._mapping = mapping
        self._rows = rows or []
        self.rowcount = rowcount

    def mappings(self):
        return self

    def fetchone(self):
        return self._mapping

    def fetchall(self):
        return self._rows


class _RepoDB:
    def __init__(self):
        self.calls = []
        self.commits = 0
        self.case_id = uuid4()

    async def execute(self, query, params):
        query_text = str(query)
        params = params.copy()
        self.calls.append((query_text, params))

        if "INSERT INTO cases" in query_text:
            return _MappingResult({"id": self.case_id, **params})
        if "SELECT" in query_text and "WHERE alert_id" in query_text:
            return _MappingResult({"id": self.case_id, "alert_id": params["alert_id"]})
        if "SELECT" in query_text:
            return _MappingResult(rows=[{"id": self.case_id, **params}])
        return _MappingResult(rowcount=1)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_case_repository_creates_joinable_case_metadata():
    db = _RepoDB()
    repo = CaseRepository(db)
    timestamp = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)
    qdrant_point_id = uuid4()

    row = await repo.create_case(
        store_id=3,
        camera_id=12,
        alert_id=99,
        timestamp=timestamp,
        behavior_scores={"item_pickup": 0.8, "looking_around": 0.4},
        pose_sequence_path="s3://bucket/pose.json",
        clip_path="s3://bucket/clip.mp4",
        keyframe_paths=["s3://bucket/k1.jpg", "s3://bucket/k2.jpg"],
        qdrant_point_id=qdrant_point_id,
    )

    assert isinstance(row["id"], UUID)
    assert row["store_id"] == 3
    assert row["camera_id"] == 12
    assert row["alert_id"] == 99
    assert row["behavior_scores"]["item_pickup"] == 0.8
    assert row["keyframe_paths"] == ["s3://bucket/k1.jpg", "s3://bucket/k2.jpg"]
    assert row["qdrant_point_id"] == qdrant_point_id
    assert db.commits == 1


@pytest.mark.asyncio
async def test_case_repository_updates_label_vlm_and_qdrant_reference():
    db = _RepoDB()
    repo = CaseRepository(db)
    case_id = uuid4()
    qdrant_point_id = uuid4()

    labeled = await repo.update_label(
        case_id=case_id,
        label="false_positive",
        label_confidence=0.9,
        labeled_by=7,
        labeled_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
    )
    vlm = await repo.update_vlm_verdict(
        case_id=case_id,
        is_suspicious=False,
        confidence=0.2,
        reason="normal browsing",
    )
    attached = await repo.attach_qdrant_point(
        case_id=case_id,
        qdrant_point_id=qdrant_point_id,
    )

    assert labeled is True
    assert vlm is True
    assert attached is True
    assert db.calls[0][1]["label"] == "false_positive"
    assert db.calls[1][1]["is_suspicious"] is False
    assert db.calls[2][1]["qdrant_point_id"] == qdrant_point_id
    assert db.commits == 3


@pytest.mark.asyncio
async def test_case_repository_lists_unlabeled_by_store():
    db = _RepoDB()
    repo = CaseRepository(db)

    rows = await repo.list_unlabeled(store_id=3, limit=10)

    assert rows == [{"id": db.case_id, "store_id": 3, "limit": 10}]
    query, params = db.calls[0]
    assert "WHERE store_id = :store_id" in query
    assert "label = 'unlabeled'" in query
    assert params == {"store_id": 3, "limit": 10}
