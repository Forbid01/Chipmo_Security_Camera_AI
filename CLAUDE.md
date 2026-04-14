# Chipmo Security Camera AI

## Architecture
- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic migrations
- **Frontend**: React 19, Vite, TailwindCSS v4, Zustand
- **Database**: PostgreSQL (asyncpg)
- **AI/ML**: YOLO11 (Ultralytics), PyTorch, auto-learning from feedback
- **Deployment**: Docker Compose, GitHub Actions CI/CD

## Project Structure
```
shoplift_detector/          # Backend
  app/
    api/v1/                 # Versioned API (new)
    api/                    # Legacy endpoints (backward compat)
    core/                   # Config, security, logging
    db/models/              # SQLAlchemy ORM models
    db/repository/          # Data access layer
    schemas/                # Pydantic request/response models
    services/               # Business logic (AI, cameras, alerts, auto-learning)
  main.py                   # Entry point
security-web/               # Frontend (React)
tests/                      # Pytest test suite
alembic/                    # Database migrations
```

## Key Commands
```bash
# Development
pip install -r requirements.txt
alembic upgrade head
python shoplift_detector/main.py

# Testing
pytest --cov=shoplift_detector tests/

# Linting
ruff check shoplift_detector/
ruff format shoplift_detector/

# Docker
docker-compose up -d
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Frontend
cd security-web && npm install && npm run build

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## API Structure
- `POST /token` - Login (legacy, also at `/api/v1/auth/token`)
- `POST /register` - Register (legacy, also at `/api/v1/auth/register`)
- `GET /api/v1/auth/me` - Current user
- `GET /api/v1/stores` - List stores
- `GET /api/v1/cameras` - List cameras
- `GET /api/v1/video/feed/{camera_id}` - Authenticated video stream
- `GET /api/v1/video/store/{store_id}` - Store grid view
- `GET /api/v1/alerts` - User alerts
- `POST /api/v1/feedback` - Alert feedback (auto-learning)
- `/api/v1/admin/*` - Admin CRUD endpoints

## Auto-Learning System
1. Staff mark alerts as true_positive/false_positive via feedback endpoint
2. After 20+ feedback items per store, auto-learner activates
3. Calculates optimal threshold and score weights per store
4. Saves learned config to model_versions table
5. AI service automatically uses learned config
6. Runs every 5 minutes in background

## Multi-tenant Architecture
Organization -> Stores -> Cameras -> Alerts
Each store has its own AI threshold and learned parameters.
