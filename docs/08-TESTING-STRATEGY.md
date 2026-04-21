# 08 — Testing Strategy

Chipmo Security Camera AI системийн чанар, найдвартай байдлыг
хангахад зориулсан тестийн стратеги.

---

## 1. Testing pyramid

```
                  ╱╲
                 ╱  ╲
                ╱ E2E╲        ~5% — end-to-end (real camera, real VLM)
               ╱──────╲
              ╱Integration╲   ~20% — DB, Redis, Qdrant, Ollama hit
             ╱──────────────╲
            ╱   Unit tests    ╲ ~60% — pure logic, fast
           ╱────────────────────╲
          ╱  Model validation   ╲~15% — AI-specific accuracy tests
         ╱──────────────────────╲
```

---

## 2. Unit tests

### Scope

- Pure logic: behavior scoring, weight calculation, FPS controller state machine
- Utility functions: brightness detection, crop extraction, embedding combiners
- Pydantic model validation
- FastAPI route handlers (with mocked DB)

### Tools

- **pytest** — framework
- **pytest-asyncio** — async tests
- **pytest-mock** — mocking
- **hypothesis** — property-based testing (behavior scoring math)
- **faker** — synthetic data

### Coverage target

- **Overall:** 80%+
- **Business logic (shoplift_detector/services):** 90%+
- **AI logic (shoplift_detector/ai):** 70%+ (models mocked)

### Example

```python
# tests/services/test_alert_manager.py

import pytest
from shoplift_detector.services.alert_manager import AlertManager, AlertState

@pytest.fixture
def manager():
    return AlertManager(cooldown_seconds=60)

async def test_first_alert_triggers(manager):
    decision = await manager.process(
        camera_id="cam1",
        person_id=42,
        score=15.0,
        threshold=10.0,
    )
    assert decision.action == "send_alert"
    assert manager.get_state("cam1", 42) == AlertState.ACTIVE

async def test_second_alert_within_cooldown_suppressed(manager, time_machine):
    # First alert
    await manager.process("cam1", 42, 15.0, 10.0)
    # End event
    await manager.resolve("cam1", 42)
    # Try again within cooldown
    time_machine.shift(30)  # 30 seconds later
    decision = await manager.process("cam1", 42, 14.0, 10.0)
    assert decision.action == "suppress"
    assert decision.reason == "cooldown_active"

async def test_alert_after_cooldown_expires(manager, time_machine):
    await manager.process("cam1", 42, 15.0, 10.0)
    await manager.resolve("cam1", 42)
    time_machine.shift(61)  # past cooldown
    decision = await manager.process("cam1", 42, 14.0, 10.0)
    assert decision.action == "send_alert"
```

### Property-based test example

```python
from hypothesis import given, strategies as st

@given(
    scores=st.lists(st.floats(min_value=0, max_value=1), min_size=6, max_size=6),
    weights=st.lists(st.floats(min_value=0.1, max_value=20), min_size=6, max_size=6),
)
def test_behavior_score_always_non_negative(scores, weights):
    result = compute_weighted_score(scores, weights)
    assert result >= 0
```

### Running

```bash
pytest tests/ -v --cov=shoplift_detector --cov-report=term --cov-report=html
```

---

## 3. Integration tests

### Scope

- FastAPI route → DB round trip
- Redis Streams pipeline
- Qdrant insert + query
- Ollama VLM wrapper (with small test model)
- Alembic migrations up/down

### Setup

`docker-compose.test.yml`:

```yaml
services:
  postgres-test:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: test
      POSTGRES_DB: chipmo_test
    tmpfs: /var/lib/postgresql/data

  redis-test:
    image: redis:7-alpine
    tmpfs: /data

  qdrant-test:
    image: qdrant/qdrant:v1.11.0
    tmpfs: /qdrant/storage
```

Fixture:

```python
# tests/conftest.py

@pytest.fixture(scope="session")
async def test_db():
    # Apply migrations
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")

    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine

    # Cleanup
    command.downgrade(alembic_cfg, "base")

@pytest.fixture
async def db_session(test_db):
    async with AsyncSession(test_db) as session:
        yield session
        await session.rollback()
```

### Example

```python
async def test_create_alert_persists_to_db(db_session, qdrant_client):
    # Given
    store = await create_test_store(db_session)
    camera = await create_test_camera(db_session, store.id)

    # When
    alert = await alert_service.create(
        session=db_session,
        store_id=store.id,
        camera_id=camera.id,
        behavior_scores={"item_pickup": 0.85, ...},
        clip_path="s3://test/clip.mp4",
    )

    # Then
    result = await db_session.execute(
        select(AlertEvent).where(AlertEvent.id == alert.id)
    )
    assert result.scalar_one().score > 10
    # Qdrant case хадгалагдсан эсэхийг шалгах
    cases = qdrant_client.scroll(
        collection_name=f"store_{store.id}_cases",
        limit=1,
    )
    assert len(cases[0]) == 1
```

---

## 4. AI model validation tests

### Scope

- YOLO detection accuracy
- Pose keypoint accuracy
- Re-ID embedding similarity
- VLM response consistency

### Test data

**Labeled test set:**
- 500+ clip (30 сек тус бүр), label-тай
- Categories:
  - `true_theft` (150)
  - `false_positive_normal` (200)
  - `false_positive_staff` (100)
  - `edge_cases` (50) — night mode, crowded, occlusion
- Location: `tests/data/ai_validation_set/` (git LFS эсвэл S3)

### Validation suite

```python
# tests/ai/test_detection_accuracy.py

@pytest.fixture(scope="module")
def validation_set():
    return load_validation_set("tests/data/ai_validation_set/")

def test_true_positive_rate(validation_set):
    true_positives = [c for c in validation_set if c.label == "true_theft"]
    detected = 0
    for clip in true_positives:
        result = run_full_pipeline(clip.path)
        if result.alert_triggered:
            detected += 1
    tpr = detected / len(true_positives)
    assert tpr >= 0.85, f"TPR {tpr} below 0.85 threshold"

def test_false_positive_rate(validation_set):
    false_cases = [c for c in validation_set if c.label.startswith("false_positive")]
    falsely_triggered = 0
    for clip in false_cases:
        result = run_full_pipeline(clip.path)
        if result.alert_triggered:
            falsely_triggered += 1
    fpr = falsely_triggered / len(false_cases)
    assert fpr <= 0.10, f"FPR {fpr} above 0.10 threshold"

def test_night_mode_no_regression(validation_set):
    night_cases = [c for c in validation_set if c.is_night]
    # Night mode-д FPR өдрийн 1.2x-аас бага байх
    # ... similar checks
```

### Regression check

Model upgrade хийх бүрт:
```bash
pytest tests/ai/ --benchmark-save=v1.2.0
pytest tests/ai/ --benchmark-compare=v1.1.0 --benchmark-fail=5%
```

---

## 5. End-to-End (E2E) tests

### Scope

- Full pipeline: RTSP stream → inference → alert → Telegram
- User dashboard flow (Playwright)
- Edge-central sync

### E2E environment

Test harness:
- 1 mock RTSP server (ffmpeg-ээр test video cycle)
- 1 edge box (virtualized or dedicated test rig)
- 1 central server (staging)
- 1 test Telegram group

### Test scenarios

```python
# tests/e2e/test_theft_detection.py

async def test_full_theft_detection_flow():
    """
    1. Start mock RTSP stream (theft-sample.mp4 loop)
    2. Edge box picks up stream
    3. YOLO detects person
    4. Behavior accumulator crosses threshold
    5. RAG passes (no matching FP)
    6. VLM confirms suspicious
    7. Alert uploaded to central
    8. Telegram notification received
    """
    # Setup
    rtsp_server = start_mock_rtsp("theft-sample.mp4")
    await wait_for_edge_online(edge_box_id)

    # Trigger
    await configure_camera(edge_box_id, rtsp_server.url)

    # Wait for alert
    alert = await wait_for_alert(store_id, timeout=60)
    assert alert.vlm_confidence > 0.5

    # Telegram delivered
    messages = await poll_test_telegram_group(timeout=30)
    assert any(f"Alert #{alert.id}" in m.text for m in messages)
```

### Dashboard E2E (Playwright)

```python
# tests/e2e/test_dashboard.py

async def test_label_an_alert(page):
    await page.goto("https://staging.chipmo.mn")
    await page.fill("#email", "test@chipmo.mn")
    await page.fill("#password", "testpass")
    await page.click("button[type=submit]")

    await page.goto("/labels/pending")
    await page.wait_for_selector("[data-test-id=label-card]")

    await page.click("[data-test-id=label-theft]")
    await expect(page.locator(".toast-success")).to_be_visible()
```

### Cadence

- PR-д: unit + integration
- Nightly: full E2E suite (~30 мин)
- Weekly: AI validation regression

---

## 6. Performance testing

### Load testing (Central API)

**Tool:** Locust

```python
# tests/load/locustfile.py

from locust import HttpUser, task, between

class EdgeBoxUser(HttpUser):
    wait_time = between(25, 35)

    @task(10)
    def heartbeat(self):
        self.client.post("/api/v1/edge/heartbeat", json={...})

    @task(2)
    def upload_alert(self):
        self.client.post("/api/v1/edge/alerts",
            files={"clip": ("test.mp4", b"...")},
            data={"metadata": "{...}"},
        )
```

**Targets:**
- Baseline: 50 concurrent edge boxes
- Stress: 500 concurrent
- P95 heartbeat latency < 200ms
- P95 alert upload latency < 2s (5MB clip)

### Inference latency benchmark

```bash
# On edge box
python benchmarks/inference_bench.py \
    --camera-count 8 \
    --duration 300 \
    --output benchmarks/results/rtx5060.json
```

**Target per frame:**
- YOLO11s-pose: < 15ms
- OSNet Re-ID: < 10ms
- RAG query: < 50ms
- VLM check: < 1000ms (p95)

### GPU memory profiling

```bash
nvidia-smi dmon -s u -i 0 -o TD > gpu_profile.txt
# during 1 hour of load
```

---

## 7. Security testing

### Static analysis

```bash
# Python
bandit -r shoplift_detector/
ruff check --select S shoplift_detector/

# Dependencies
pip-audit
safety check

# JS
npm audit
```

### SAST in CI

- GitHub CodeQL (scheduled weekly)
- Bandit on PR

### Penetration testing

Quarterly external pen-test:
- Auth flow (JWT, cookie, password reset)
- Multi-tenant isolation (store_id leakage)
- RCE via uploaded clips (video parsing)
- RTSP injection
- WireGuard key rotation

### Secret scanning

- `detect-secrets` pre-commit hook
- GitHub secret scanning enabled

---

## 8. Database testing

### Migration tests

```python
# tests/migrations/test_migrations.py

def test_upgrade_downgrade_roundtrip():
    """Бүх migration up+down-ийг дамжих."""
    for rev in list_migrations():
        command.upgrade(alembic_cfg, rev)
        command.downgrade(alembic_cfg, "-1")
        command.upgrade(alembic_cfg, rev)
```

### Data integrity

```python
def test_no_orphaned_cases():
    """Case-уудын alert_event_id бүгд валид."""
    orphans = await session.execute("""
        SELECT c.id FROM cases c
        LEFT JOIN alert_events a ON c.alert_event_id = a.id
        WHERE a.id IS NULL
    """)
    assert orphans.scalar_one_or_none() is None
```

---

## 9. Chaos / Resilience testing

### Scenarios

- Edge box power loss (mid-inference)
- Internet outage (24h → reconnect)
- Central DB failover
- Redis queue overflow
- GPU hang
- Camera RTSP hang (TCP alive but no frames)
- Disk full on edge box
- Clock skew > 5 min

### Tool: Chaos Toolkit

```yaml
# tests/chaos/edge_power_loss.yaml
version: 1.0.0
title: Edge box power loss recovery
method:
  - type: action
    name: kill-edge-container
    provider:
      type: process
      path: docker
      arguments: ["kill", "chipmo-inference"]
  - type: probe
    name: alert-pipeline-recovers
    tolerance: true
    provider:
      type: python
      module: tests.chaos.probes
      func: check_alert_pipeline_healthy
      arguments:
        timeout: 120
```

---

## 10. Accessibility testing (dashboard)

- axe-core automated checks
- Manual keyboard navigation
- Screen reader test (NVDA)
- Color contrast (WCAG AA)

---

## 11. CI/CD integration

### GitHub Actions workflows

```yaml
# .github/workflows/test.yml

on: [push, pull_request]

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements-dev.txt
      - run: pytest tests/unit/ --cov --cov-fail-under=80

  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
      redis:
        image: redis:7
      qdrant:
        image: qdrant/qdrant:v1.11.0
    steps:
      - run: pytest tests/integration/

  ai-validation:
    runs-on: [self-hosted, gpu]
    if: github.event_name == 'schedule' || contains(github.event.head_commit.message, '[ai-test]')
    steps:
      - run: pytest tests/ai/ --benchmark-compare
```

### Pre-commit hooks

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
```

---

## 12. Test data management

### Fixtures

- `tests/fixtures/stores.json` — synthetic store data
- `tests/fixtures/alerts.json` — synthetic alert events
- `tests/fixtures/pose_sequences/` — replay-able pose data

### AI test clips

- **Git LFS** для < 500MB total
- **S3** for larger (700MB-5GB per clip)
- Access token: `CHIPMO_TEST_S3_KEY` env var

### Anonymization

Test data-д бодит хүний царай, дуу байж болохгүй:
- Synthetic (DALL-E 3 generated or VFX)
- Permission-тай staff-ын тоглосон сценар
- Pre-anonymized (CV2 blur all faces before commit)

---

## 13. Test metrics & gates

### PR merge gates

- Unit tests pass
- Integration tests pass
- Coverage ≥ 80% (no decrease from main)
- No new Bandit high-severity
- No lint errors
- AI validation (if AI files touched)

### Weekly metrics to track

- Test execution time trend
- Flaky test list (retries > 2)
- Coverage trend
- AI validation accuracy over time

---

## 14. Definition of done (DOD)

Feature-ийг "done" гэж үзэхийн тулд:

- [ ] Unit test бичсэн, coverage зохих түвшинд
- [ ] Integration test (if DB/external service)
- [ ] AI validation update (if AI logic)
- [ ] Metrics / logging нэмсэн
- [ ] Documentation шинэчилсэн
- [ ] CHANGELOG-д бичсэн
- [ ] Code review + approval
- [ ] Migration (if DB change) tested up+down
- [ ] Deployment rollback plan documented

---

## Холбоотой документ

- [02-ROADMAP.md](./02-ROADMAP.md)
- [03-TECH-SPECS.md](./03-TECH-SPECS.md)
- [07-API-SPEC.md](./07-API-SPEC.md)

---

Updated: 2026-04-17
