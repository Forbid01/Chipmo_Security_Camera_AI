"""Tests for security utilities: password hashing, JWT tokens, password validation."""

import os
import sys
import time
import pytest
from datetime import timedelta
from fastapi import HTTPException

# Ensure imports work
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOPLIFT_DIR = os.path.join(BASE_DIR, "shoplift_detector")
if SHOPLIFT_DIR not in sys.path:
    sys.path.insert(0, SHOPLIFT_DIR)

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")

from shoplift_detector.app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    validate_password_strength,
    _decode_token,
    MIN_PASSWORD_LENGTH,
    SECRET_KEY,
    ALGORITHM,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    """Tests for bcrypt password hashing / verification."""

    @pytest.mark.security
    def test_hash_and_verify_correct_password(self):
        """A hashed password should verify against the original plaintext."""
        plain = "MySecureP@ss1!"
        hashed = get_password_hash(plain)
        assert verify_password(plain, hashed) is True

    @pytest.mark.security
    def test_hash_does_not_verify_wrong_password(self):
        """A different plaintext must not verify against the hash."""
        hashed = get_password_hash("CorrectP@ss1!")
        assert verify_password("WrongP@ss1!", hashed) is False

    @pytest.mark.security
    def test_hash_is_not_plaintext(self):
        """The hash output must not equal the original password."""
        plain = "MySecureP@ss1!"
        hashed = get_password_hash(plain)
        assert hashed != plain

    @pytest.mark.security
    def test_different_hashes_for_same_password(self):
        """Bcrypt produces a unique salt each time, so two hashes differ."""
        plain = "MySecureP@ss1!"
        h1 = get_password_hash(plain)
        h2 = get_password_hash(plain)
        assert h1 != h2
        # Both should still verify
        assert verify_password(plain, h1) is True
        assert verify_password(plain, h2) is True

    @pytest.mark.security
    def test_long_password_truncated_to_72_bytes(self):
        """Passwords longer than 72 bytes are truncated (bcrypt limit)."""
        long_pw = "A" * 100 + "!1a"
        hashed = get_password_hash(long_pw)
        # The function truncates to 72 chars before hashing
        assert verify_password(long_pw[:72], hashed) is True


# ---------------------------------------------------------------------------
# JWT token creation / decode
# ---------------------------------------------------------------------------

class TestJWTTokens:
    """Tests for create_access_token and _decode_token."""

    @pytest.mark.security
    def test_create_and_decode_token(self):
        """A token created with sub/role/org_id can be decoded back."""
        token = create_access_token(data={
            "sub": "alice",
            "role": "admin",
            "org_id": 5,
            "user_id": 10,
        })
        decoded = _decode_token(token)
        assert decoded["username"] == "alice"
        assert decoded["role"] == "admin"
        assert decoded["org_id"] == 5
        assert decoded["user_id"] == 10

    @pytest.mark.security
    def test_token_with_custom_expiry(self):
        """A token with a custom expiry delta still decodes before expiry."""
        token = create_access_token(
            data={"sub": "bob", "role": "user", "org_id": None, "user_id": 2},
            expires_delta=timedelta(hours=2),
        )
        decoded = _decode_token(token)
        assert decoded["username"] == "bob"

    @pytest.mark.security
    def test_expired_token_raises(self):
        """An already-expired token raises HTTPException (401)."""
        token = create_access_token(
            data={"sub": "expired_user", "role": "user", "org_id": None, "user_id": 3},
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(HTTPException) as exc_info:
            _decode_token(token)
        assert exc_info.value.status_code == 401

    @pytest.mark.security
    def test_tampered_token_raises(self):
        """A token with an altered payload raises HTTPException."""
        token = create_access_token(data={"sub": "real", "role": "user"})
        # Flip a character in the payload section
        parts = token.split(".")
        parts[1] = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
        tampered = ".".join(parts)
        with pytest.raises(HTTPException) as exc_info:
            _decode_token(tampered)
        assert exc_info.value.status_code == 401

    @pytest.mark.security
    def test_token_without_sub_raises(self):
        """A token missing the 'sub' claim raises HTTPException."""
        import jwt as pyjwt

        payload = {"role": "user", "org_id": None}
        # Manually encode without 'sub'
        token = pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        with pytest.raises(HTTPException) as exc_info:
            _decode_token(token)
        assert exc_info.value.status_code == 401

    @pytest.mark.security
    def test_garbage_string_raises(self):
        """A completely invalid string raises HTTPException."""
        with pytest.raises(HTTPException):
            _decode_token("this.is.not.a.jwt")


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

class TestPasswordValidation:
    """Tests for validate_password_strength."""

    @pytest.mark.security
    def test_valid_password_passes(self):
        """A strong password should not raise."""
        validate_password_strength("StrongP@ss1!")  # should not raise

    @pytest.mark.security
    def test_too_short_password(self):
        """Password shorter than MIN_PASSWORD_LENGTH raises 400."""
        with pytest.raises(HTTPException) as exc_info:
            validate_password_strength("Ab1!")
        assert exc_info.value.status_code == 400

    @pytest.mark.security
    def test_no_uppercase(self):
        """Password without uppercase letter raises 400."""
        with pytest.raises(HTTPException) as exc_info:
            validate_password_strength("alllower1!aa")
        assert exc_info.value.status_code == 400

    @pytest.mark.security
    def test_no_lowercase(self):
        """Password without lowercase letter raises 400."""
        with pytest.raises(HTTPException) as exc_info:
            validate_password_strength("ALLUPPER1!AA")
        assert exc_info.value.status_code == 400

    @pytest.mark.security
    def test_no_digit(self):
        """Password without any digit raises 400."""
        with pytest.raises(HTTPException) as exc_info:
            validate_password_strength("NoDigits!@Ab")
        assert exc_info.value.status_code == 400

    @pytest.mark.security
    def test_no_special_char(self):
        """Password without special character raises 400."""
        with pytest.raises(HTTPException) as exc_info:
            validate_password_strength("NoSpecial1Aa")
        assert exc_info.value.status_code == 400

    @pytest.mark.security
    def test_exactly_min_length_valid(self):
        """Password at exactly MIN_PASSWORD_LENGTH with all requirements passes."""
        # 8 chars: upper + lower + digit + special
        validate_password_strength("Abcd1!ef")  # should not raise

    @pytest.mark.security
    def test_empty_password(self):
        """Empty password raises 400."""
        with pytest.raises(HTTPException) as exc_info:
            validate_password_strength("")
        assert exc_info.value.status_code == 400
