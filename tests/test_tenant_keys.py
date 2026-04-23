"""Tests for T1-12 — tenant-namespaced Redis key builder."""

from uuid import UUID, uuid4

import pytest

from shoplift_detector.app.core.tenant_keys import NAMESPACE_PREFIX, TenantKeys


TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------

def test_accepts_uuid_instance():
    uid = uuid4()
    keys = TenantKeys(tenant_id=uid)
    assert keys.tenant_id == str(uid)


def test_accepts_uuid_string():
    keys = TenantKeys(tenant_id=TENANT_A)
    assert keys.tenant_id == TENANT_A


def test_canonicalizes_uppercase_uuid_to_lowercase():
    keys = TenantKeys(tenant_id=TENANT_A.upper())
    assert keys.tenant_id == TENANT_A


def test_rejects_empty_tenant_id():
    with pytest.raises(ValueError):
        TenantKeys(tenant_id="")


def test_rejects_whitespace_tenant_id():
    with pytest.raises(ValueError):
        TenantKeys(tenant_id="   ")


def test_rejects_non_uuid_string():
    # A bare integer-ish string is a common mistake (passing store_id
    # by accident). Must fail loudly.
    with pytest.raises(ValueError):
        TenantKeys(tenant_id="42")


def test_rejects_non_string_non_uuid_input():
    with pytest.raises(TypeError):
        TenantKeys(tenant_id=42)  # type: ignore[arg-type]


def test_is_frozen_dataclass():
    keys = TenantKeys(tenant_id=TENANT_A)
    with pytest.raises(Exception):
        keys.tenant_id = TENANT_B  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Key format
# ---------------------------------------------------------------------------

def test_person_state_matches_canonical_doc_format():
    keys = TenantKeys(tenant_id=TENANT_A)
    key = keys.person_state(store_id=42, person_id="P-1")
    assert key == f"tenant:{TENANT_A}:store:42:person:P-1"


def test_camera_state_format():
    keys = TenantKeys(tenant_id=TENANT_A)
    assert keys.camera_state(camera_id=7) == f"tenant:{TENANT_A}:camera:7:state"


def test_store_scope_is_prefix_for_callers():
    keys = TenantKeys(tenant_id=TENANT_A)
    assert keys.store_scope(store_id=1) == f"tenant:{TENANT_A}:store:1"


def test_rate_limit_key_embeds_tenant_but_uses_ratelimit_root():
    keys = TenantKeys(tenant_id=TENANT_A)
    assert keys.rate_limit(action="api_call", bucket=12345) == (
        f"ratelimit:{TENANT_A}:api_call:12345"
    )


def test_reid_collection_hyphens_become_underscores():
    # Qdrant collection names reject `-` in some versions.
    keys = TenantKeys(tenant_id=TENANT_A)
    assert keys.reid_collection_name() == (
        f"reid_tenant_{TENANT_A.replace('-', '_')}"
    )


# ---------------------------------------------------------------------------
# Misuse protection
# ---------------------------------------------------------------------------

def test_empty_segment_refused_to_prevent_global_keys():
    keys = TenantKeys(tenant_id=TENANT_A)
    # Passing an empty string into the builder would produce
    # `tenant:{uuid}:store::person:P-1` — a subtly broken key that
    # could alias across stores. The `_scoped` helper must reject.
    with pytest.raises(ValueError):
        keys.person_state(store_id="", person_id="P-1")  # type: ignore[arg-type]


def test_namespace_prefix_constant():
    assert NAMESPACE_PREFIX == "tenant"


def test_keys_for_different_tenants_never_collide():
    a = TenantKeys(tenant_id=TENANT_A)
    b = TenantKeys(tenant_id=TENANT_B)
    assert a.person_state(store_id=1, person_id="P-1") != b.person_state(
        store_id=1, person_id="P-1"
    )
    assert a.camera_state(camera_id=1) != b.camera_state(camera_id=1)
    assert a.rate_limit(action="api", bucket=1) != b.rate_limit(
        action="api", bucket=1
    )


def test_integer_segments_render_as_plain_numbers():
    # str(42) not repr(42) — renders `42` not `<int 42>`.
    keys = TenantKeys(tenant_id=TENANT_A)
    assert keys.person_state(store_id=42, person_id="P-1").endswith(
        "store:42:person:P-1"
    )
