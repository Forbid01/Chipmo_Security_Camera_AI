"""Chipmo management CLI.

Usage:
    python -m shoplift_detector.cli migrate
    python -m shoplift_detector.cli health
    python -m shoplift_detector.cli create-admin --username alice --email a@x.com --password ...
    python -m shoplift_detector.cli list-cameras
    python -m shoplift_detector.cli storage-check
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import typer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

app = typer.Typer(help="Chipmo Security AI — management CLI")


@app.command()
def migrate(message: str | None = typer.Option(None, "--message", "-m")):
    """Run Alembic migrations (upgrade head), or create a new revision with -m."""
    project_root = os.path.dirname(BASE_DIR)
    if message:
        typer.echo(f"Creating revision: {message}")
        rc = subprocess.call(
            ["alembic", "revision", "--autogenerate", "-m", message],
            cwd=project_root,
        )
    else:
        typer.echo("Upgrading to head")
        rc = subprocess.call(["alembic", "upgrade", "head"], cwd=project_root)
    raise typer.Exit(code=rc)


@app.command()
def health():
    """Check DB connectivity, storage backend, and camera config."""
    from app.core.config import settings
    from app.db.session import engine
    from app.services.storage import get_storage
    from sqlalchemy import text

    async def check_db() -> bool:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            typer.secho(f"DB check failed: {exc}", fg=typer.colors.RED)
            return False

    db_ok = asyncio.run(check_db())
    typer.echo(f"database : {'OK' if db_ok else 'FAIL'}")

    storage = get_storage()
    typer.echo(f"storage  : {type(storage).__name__} (backend={settings.STORAGE_BACKEND})")
    typer.echo(f"version  : {settings.APP_VERSION}")
    typer.echo(f"ai_learn : {settings.AI_AUTO_LEARN}")
    typer.echo(f"cooldown : {settings.AI_ALERT_COOLDOWN}s")
    raise typer.Exit(code=0 if db_ok else 1)


@app.command("create-admin")
def create_admin(
    username: str = typer.Option(..., "--username"),
    email: str = typer.Option(..., "--email"),
    password: str = typer.Option(..., "--password", prompt=True, hide_input=True),
    full_name: str | None = typer.Option(None, "--full-name"),
):
    """Create a super_admin user."""
    from app.core.security import get_password_hash
    from app.db.repository.users import UserRepository
    from app.db.session import AsyncSessionLocal

    async def _run():
        async with AsyncSessionLocal() as db:
            repo = UserRepository(db)
            existing = await repo.get_by_identifier(username)
            if existing:
                typer.secho(f"User '{username}' already exists", fg=typer.colors.YELLOW)
                return 1
            user_id = await repo.create(
                username=username,
                email=email,
                phone_number=None,
                hashed_password=get_password_hash(password),
                full_name=full_name or username,
                role="super_admin",
            )
            typer.secho(f"Created super_admin id={user_id}", fg=typer.colors.GREEN)
            return 0

    raise typer.Exit(code=asyncio.run(_run()))


@app.command("list-cameras")
def list_cameras():
    """List cameras currently configured in the database."""
    from app.db.repository.camera_repo import CameraRepository
    from app.db.session import AsyncSessionLocal

    async def _run():
        async with AsyncSessionLocal() as db:
            cams = await CameraRepository(db).get_active_cameras()
        for c in cams:
            typer.echo(
                f"  [{c['id']:>4}] store={c.get('store_id'):>4} "
                f"name={c['name']:<24} type={c.get('camera_type'):<6} "
                f"ai={c.get('is_ai_enabled', True)} url={c['url']}"
            )
        typer.echo(f"total: {len(cams)}")
        return 0

    raise typer.Exit(code=asyncio.run(_run()))


@app.command("storage-check")
def storage_check():
    """Verify the configured storage backend can upload a test blob."""
    import numpy as np
    from app.services.storage import get_storage

    try:
        backend = get_storage()
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        url = backend.save_image(frame, filename="chipmo_healthcheck.jpg")
        typer.secho(f"OK — uploaded to: {url}", fg=typer.colors.GREEN)
        raise typer.Exit(code=0)
    except typer.Exit:
        raise
    except Exception as exc:
        typer.secho(f"FAIL — {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
