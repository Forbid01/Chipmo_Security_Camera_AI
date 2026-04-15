"""Pluggable media storage — local FS, Cloudinary, S3.

Railway's filesystem is ephemeral; persistent alert media must land in object
storage. Select a backend via settings.STORAGE_BACKEND ∈ {local, cloudinary, s3}.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from io import BytesIO

from app.core.config import ALERTS_DIR, settings

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Upload bytes and return a stable URL."""

    @abstractmethod
    def save_bytes(self, data: bytes, key: str, content_type: str = "image/jpeg") -> str:
        ...

    def save_image(self, frame, filename: str | None = None) -> str:
        """Encode and upload an OpenCV BGR frame. Returns a URL."""
        import cv2

        key = filename or f"{uuid.uuid4().hex}.jpg"
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError("cv2.imencode failed")
        return self.save_bytes(buf.tobytes(), key, content_type="image/jpeg")


class LocalStorage(StorageBackend):
    """Writes to ALERTS_DIR and returns a /static/ URL."""

    def __init__(self, base_dir: str = ALERTS_DIR, base_url: str = ""):
        self.base_dir = base_dir
        self.base_url = base_url.rstrip("/")
        os.makedirs(self.base_dir, exist_ok=True)

    def save_bytes(self, data: bytes, key: str, content_type: str = "image/jpeg") -> str:
        path = os.path.join(self.base_dir, os.path.basename(key))
        with open(path, "wb") as f:
            f.write(data)
        if self.base_url:
            return f"{self.base_url}/static/{os.path.basename(key)}"
        return path


class CloudinaryStorage(StorageBackend):
    def __init__(self, cloudinary_url: str, folder: str):
        import cloudinary

        cloudinary.config(cloudinary_url=cloudinary_url, secure=True)
        self._cloudinary = cloudinary
        self.folder = folder

    def save_bytes(self, data: bytes, key: str, content_type: str = "image/jpeg") -> str:
        import cloudinary.uploader

        public_id = os.path.splitext(os.path.basename(key))[0]
        result = cloudinary.uploader.upload(
            BytesIO(data),
            public_id=public_id,
            folder=self.folder,
            resource_type="image",
            overwrite=False,
        )
        return result["secure_url"]


class S3Storage(StorageBackend):
    def __init__(self, bucket: str, region: str, prefix: str,
                 endpoint_url: str | None = None):
        import boto3

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self._endpoint = endpoint_url
        self._region = region

    def save_bytes(self, data: bytes, key: str, content_type: str = "image/jpeg") -> str:
        object_key = f"{self.prefix}/{os.path.basename(key)}" if self.prefix else os.path.basename(key)
        self._client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
            ACL="public-read",
        )
        if self._endpoint:
            return f"{self._endpoint.rstrip('/')}/{self.bucket}/{object_key}"
        return f"https://{self.bucket}.s3.{self._region}.amazonaws.com/{object_key}"


_storage_lock = threading.Lock()
_storage_instance: StorageBackend | None = None


def _build_storage() -> StorageBackend:
    backend = (settings.STORAGE_BACKEND or "local").lower()
    try:
        if backend == "cloudinary":
            if not settings.CLOUDINARY_URL:
                raise ValueError("CLOUDINARY_URL not set")
            return CloudinaryStorage(settings.CLOUDINARY_URL, settings.CLOUDINARY_FOLDER)
        if backend == "s3":
            if not settings.S3_BUCKET:
                raise ValueError("S3_BUCKET not set")
            return S3Storage(
                bucket=settings.S3_BUCKET,
                region=settings.S3_REGION,
                prefix=settings.S3_PREFIX,
                endpoint_url=settings.S3_ENDPOINT_URL,
            )
    except Exception as exc:
        logger.error(
            "storage_backend_init_failed backend=%s err=%s — falling back to local",
            backend, exc,
        )
    return LocalStorage(base_dir=ALERTS_DIR, base_url=settings.PUBLIC_BASE_URL)


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    global _storage_instance
    with _storage_lock:
        if _storage_instance is None:
            _storage_instance = _build_storage()
            logger.info(
                "storage_backend_ready kind=%s",
                type(_storage_instance).__name__,
            )
    return _storage_instance
