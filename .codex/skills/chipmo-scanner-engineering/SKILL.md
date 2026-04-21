---
name: chipmo-scanner-engineering
description: Project-specific engineering workflow for the Chipmo Scanner / Chipmo Security AI codebase. Use when Codex works in `/Users/amarmurunmandakh/Documents/Scanner` on backend FastAPI code, React/Vite frontend code, AI/camera pipeline, database migrations, docs/TASKS planning, edge/RAG/VLM roadmap work, tests, linting, deployment files, or code review for this repository.
---

# Chipmo Scanner Engineering

## Overview

Use this skill to work safely and consistently on the Chipmo Scanner repository. Treat the repo docs as the product plan, but verify every implementation detail against the current code before editing.

## First Steps

1. Confirm the workspace is `/Users/amarmurunmandakh/Documents/Scanner`.
2. Check `git status --short` before editing. Do not revert user or generated changes unless explicitly asked.
3. Read the relevant docs before making architecture or roadmap decisions:
   - `docs/README.md`
   - `docs/01-ARCHITECTURE.md`
   - `docs/02-ROADMAP.md`
   - `docs/03-TECH-SPECS.md`
   - `docs/04-EDGE-DEPLOYMENT.md`
   - `docs/05-MIGRATION-PLAN.md`
   - `docs/06-DATABASE-SCHEMA.md`
   - `docs/TASKS.md`
4. Read the implementation files that actually own the behavior. Do not rely on docs paths blindly.
5. State mismatches between docs and code clearly before implementing against the docs.

## Repo Map

- Backend entrypoint: `shoplift_detector/main.py`
- Backend API routers: `shoplift_detector/app/api/v1/`
- Backend services: `shoplift_detector/app/services/`
- Backend models: `shoplift_detector/app/db/models/`
- Backend repositories: `shoplift_detector/app/db/repository/`
- Config/security/logging: `shoplift_detector/app/core/`
- Alembic migrations: `alembic/versions/`
- Tests: `tests/`
- Frontend app: `security-web/`
- Frontend API client: `security-web/src/services/api.js`
- Planning docs: `docs/`

Important current mismatch: many docs describe target architecture and may use future names like `alert_events`, UUID IDs, `shoplift_detector/ai/...`, or `shoplift_detector/services/...`. Current code uses integer IDs, `alerts`, and `shoplift_detector/app/...` paths.

## Working Rules

- Prefer small, testable changes that match existing FastAPI, SQLAlchemy async, repository, and React patterns.
- Use `rg` / `rg --files` first for discovery.
- Use `apply_patch` for manual edits.
- Keep docs, migrations, code, and tests consistent when changing behavior.
- Treat edge, RAG, VLM, TimescaleDB, Qdrant, and Prometheus items as roadmap features unless code proves they exist.
- Preserve legacy endpoints in `shoplift_detector/main.py` unless the user explicitly asks to remove backward compatibility.
- Do not import heavy AI libraries in test startup unless mocked or guarded; tests should be able to run without camera/GPU side effects.
- For DB changes, create Alembic migrations and update SQLAlchemy models/repositories together.
- For frontend changes, preserve existing React/Vite structure under `security-web/src`.
- For user-facing UI work, follow the global frontend guidance from the system instructions.

## Common Workflows

### Updating `docs/TASKS.md`

1. Read every file in `docs/`.
2. Separate AS-IS work from TO-BE roadmap work.
3. Use stable task IDs, priority, status, dependency, and acceptance criteria.
4. Keep file paths aligned with the actual repo.
5. Include baseline tasks when lint/tests/builds are failing.

### Implementing Backend Features

1. Find the owning API router, service, repository, model, and schema.
2. Check whether legacy root endpoints and `/api/v1` endpoints both need updates.
3. Add or update tests near `tests/`.
4. Run the narrowest useful backend checks.

### Implementing AI / Camera Pipeline Features

1. Inspect `shoplift_detector/app/services/ai_service.py` and `camera_manager.py`.
2. Avoid changes that force GPU/camera access during import or test collection.
3. Make state explicit and testable; avoid only in-memory behavior for production-critical alerting.
4. Add metrics/logging where production diagnosis matters.

### Implementing Frontend Features

1. Inspect `security-web/src/services/api.js` before adding endpoints.
2. Update routes in `security-web/src/App.jsx` when adding pages.
3. Reuse existing page/component patterns.
4. Run `npm run lint` and `npm run build` from `security-web/`.

## Verification Commands

Use the smallest relevant set:

```bash
python3.12 -m pytest -q
python3.12 -m ruff check .
npm run lint
npm run build
```

Run frontend commands in `security-web/`. If backend tests fail because dependencies such as `torch` are missing, report that plainly and do not hide the failure.

## Reporting

- Summarize changed files and verification results.
- Mention tests or checks that could not run and why.
- Highlight docs/code mismatches as risks, not as completed work.
- Keep final responses concise and focused on what changed.
