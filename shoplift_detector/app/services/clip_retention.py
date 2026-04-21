import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import ALERTS_DIR, settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".webm"}


@dataclass(frozen=True)
class RetentionPolicy:
    normal_hours: float
    alert_days: float


@dataclass
class RetentionCleanupResult:
    scanned: int = 0
    deleted: int = 0
    kept_labeled: int = 0
    kept_alert: int = 0
    kept_fresh_normal: int = 0
    skipped_remote: int = 0
    errors: int = 0


class ClipRetentionCleaner:
    def __init__(
        self,
        media_dirs: list[Path] | None = None,
        policy: RetentionPolicy | None = None,
    ):
        self.media_dirs = media_dirs or [Path(ALERTS_DIR)]
        self.policy = policy or RetentionPolicy(
            normal_hours=settings.NORMAL_CLIP_RETENTION_HOURS,
            alert_days=settings.ALERT_CLIP_RETENTION_DAYS,
        )

    async def cleanup(
        self,
        db: AsyncSession,
        *,
        now: datetime | None = None,
    ) -> RetentionCleanupResult:
        now = self._normalize_datetime(now) or datetime.now(UTC)
        protected = await self._load_protected_paths(db, now=now)
        return self.cleanup_files(
            labeled_paths=protected["labeled"],
            alert_paths=protected["alert"],
            now=now,
        )

    def cleanup_files(
        self,
        *,
        labeled_paths: set[Path],
        alert_paths: set[Path],
        now: datetime,
    ) -> RetentionCleanupResult:
        result = RetentionCleanupResult()
        normal_cutoff = now - timedelta(hours=self.policy.normal_hours)

        for media_dir in self.media_dirs:
            if not media_dir.exists():
                continue
            for path in media_dir.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:
                    continue

                result.scanned += 1
                resolved = path.resolve()
                if resolved in labeled_paths:
                    result.kept_labeled += 1
                    continue
                if resolved in alert_paths:
                    result.kept_alert += 1
                    continue

                try:
                    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                    if modified_at > normal_cutoff:
                        result.kept_fresh_normal += 1
                        continue
                    path.unlink()
                    result.deleted += 1
                except OSError as exc:
                    result.errors += 1
                    logger.warning("clip_retention_delete_failed path=%s err=%s", path, exc)

        return result

    async def _load_protected_paths(
        self,
        db: AsyncSession,
        *,
        now: datetime,
    ) -> dict[str, set[Path]]:
        alert_cutoff = now - timedelta(days=self.policy.alert_days)
        query = text("""
            SELECT
                a.image_path,
                a.video_path,
                a.event_time,
                af.alert_id IS NOT NULL AS is_labeled
            FROM alerts a
            LEFT JOIN alert_feedback af ON af.alert_id = a.id
            WHERE a.image_path IS NOT NULL OR a.video_path IS NOT NULL
        """)
        result = await db.execute(query)
        labeled_paths: set[Path] = set()
        alert_paths: set[Path] = set()

        for row in result.mappings().fetchall():
            event_time = self._normalize_datetime(row.get("event_time"))
            paths = [
                self._resolve_media_path(row.get("image_path")),
                self._resolve_media_path(row.get("video_path")),
            ]
            for path in paths:
                if path is None:
                    continue
                if row.get("is_labeled"):
                    labeled_paths.add(path)
                elif event_time and event_time >= alert_cutoff:
                    alert_paths.add(path)

        return {"labeled": labeled_paths, "alert": alert_paths}

    def _resolve_media_path(self, value: str | None) -> Path | None:
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https", "s3", "gs"}:
            return None

        raw_path = parsed.path if parsed.scheme == "file" else value
        candidate = Path(raw_path)
        if candidate.is_absolute() and candidate.exists():
            return candidate.resolve()

        name = os.path.basename(raw_path)
        if not name:
            return None

        for media_dir in self.media_dirs:
            path = media_dir / name
            if path.exists():
                return path.resolve()
        return None

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


clip_retention_cleaner = ClipRetentionCleaner()
