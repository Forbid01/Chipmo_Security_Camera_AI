"""Tenant-namespaced Redis key builder (T1-12, DOC-05 §3.3).

All Redis keys in the system must start with `tenant:{uuid}:` so a
lookup for tenant A can never touch tenant B's data. This module
centralizes the format so no handler is tempted to sprintf its own
string.

Misuse protection (enforced by unit tests):
- Empty / whitespace-only tenant_id rejected at construction.
- UUID inputs are coerced to canonical string, so the same tenant
  gets the same key whether callers pass `UUID(...)`, raw hex, or
  the DB string representation.
- Keys are built through methods — no `__str__` on the namespace
  that could leak the raw tenant prefix as a usable key.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

NAMESPACE_PREFIX = "tenant"


def _canonicalize(tenant_id: UUID | str) -> str:
    """Normalize UUID input to the canonical lowercase hyphenated form.

    Raises ValueError on empty/whitespace so a caller forgetting to
    pass tenant_id fails loudly instead of producing a global key
    like `tenant::store:1:person:P-1`.
    """
    if isinstance(tenant_id, UUID):
        return str(tenant_id)
    if not isinstance(tenant_id, str):
        raise TypeError(
            f"tenant_id must be str or UUID, got {type(tenant_id).__name__}"
        )
    stripped = tenant_id.strip()
    if not stripped:
        raise ValueError("tenant_id must not be empty")
    # Validate UUID shape — catches typos like store_id being passed
    # where tenant_id was expected.
    try:
        return str(UUID(stripped))
    except ValueError as exc:
        raise ValueError(
            f"tenant_id must be a UUID, got {tenant_id!r}"
        ) from exc


@dataclass(frozen=True)
class TenantKeys:
    """Per-tenant Redis key factory.

    Usage:
        keys = TenantKeys(tenant_id=tenant["tenant_id"])
        await redis.set(keys.person_state(store_id=42, person_id="P-1"), ...)
    """

    tenant_id: str

    def __post_init__(self) -> None:
        # Frozen dataclass hack: force canonicalization.
        object.__setattr__(self, "tenant_id", _canonicalize(self.tenant_id))

    # ------------------------------------------------------------------
    # Key builders — always prefix with tenant:{uuid}:
    # ------------------------------------------------------------------

    def _scoped(self, *parts: str | int) -> str:
        """Join the tenant prefix with extra segments. Coerces ints to
        str so camera_id=42 renders as `42` not `<int 42>`."""
        tokens = [NAMESPACE_PREFIX, self.tenant_id]
        for part in parts:
            if part is None or part == "":
                raise ValueError("empty key segment would collide")
            tokens.append(str(part))
        return ":".join(tokens)

    def person_state(self, *, store_id: int, person_id: str) -> str:
        """DOC-05 §3.3 canonical form:
        `tenant:{uuid}:store:{store_id}:person:{person_id}`"""
        return self._scoped("store", store_id, "person", person_id)

    def camera_state(self, *, camera_id: int) -> str:
        return self._scoped("camera", camera_id, "state")

    def store_scope(self, *, store_id: int) -> str:
        """Open-ended store scope — callers append their own suffix."""
        return self._scoped("store", store_id)

    def rate_limit(self, *, action: str, bucket: int) -> str:
        # Rate-limit keys use a different root prefix (`ratelimit:`)
        # but still embed the tenant id. Kept here so all tenant
        # namespacing lives in one module.
        return f"ratelimit:{self.tenant_id}:{action}:{bucket}"

    def reid_collection_name(self) -> str:
        """Qdrant collection name for per-tenant Re-ID embeddings.
        Hyphens collapsed to underscores — Qdrant rejects `-` in names.
        """
        return f"reid_tenant_{self.tenant_id.replace('-', '_')}"
