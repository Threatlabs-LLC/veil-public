"""Offline license validation using RS256 JWT.

The public key ships with the Docker image.
The private key stays with the VeilChat business.
No phone-home. No internet required.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LicenseClaims:
    """Validated license claims."""
    org_id: str
    org_name: str
    tier: str
    max_users: int
    features: list[str]
    issued_at: int
    expires_at: int
    license_id: str

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def days_remaining(self) -> int:
        remaining = (self.expires_at - time.time()) / 86400
        return max(0, int(remaining))


class LicenseError(Exception):
    """Base license error."""
    pass


class LicenseInvalidError(LicenseError):
    """License key is malformed or signature is invalid."""
    pass


class LicenseExpiredError(LicenseError):
    """License key has expired."""
    pass


class LicenseValidator:
    """Validates license JWTs using RS256 public key.

    The validation is fully offline — no network calls.
    """

    def __init__(self, public_key_pem: str | None = None, public_key_path: str | None = None):
        if public_key_pem:
            self._public_key = public_key_pem
        elif public_key_path:
            self._public_key = Path(public_key_path).read_text()
        else:
            self._public_key = None

    @property
    def is_configured(self) -> bool:
        return self._public_key is not None

    def validate(self, token: str) -> LicenseClaims:
        """Validate a license JWT and return claims.

        Raises LicenseInvalidError or LicenseExpiredError on failure.
        """
        if not self._public_key:
            raise LicenseInvalidError("License validation not configured (no public key)")

        try:
            import jwt as pyjwt
            claims = pyjwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],
                options={"require": ["sub", "tier", "exp", "iat", "jti"]},
            )
        except ImportError:
            # Fallback: manual base64 decode + signature skip for dev
            raise LicenseInvalidError(
                "PyJWT with cryptography is required for license validation. "
                "Install with: pip install PyJWT[crypto]"
            )
        except Exception as e:
            raise LicenseInvalidError(f"Invalid license key: {e}")

        # Check expiration
        if time.time() > claims.get("exp", 0):
            raise LicenseExpiredError("License has expired")

        return LicenseClaims(
            org_id=claims["sub"],
            org_name=claims.get("org_name", ""),
            tier=claims["tier"],
            max_users=claims.get("max_users", 3),
            features=claims.get("features", []),
            issued_at=claims["iat"],
            expires_at=claims["exp"],
            license_id=claims["jti"],
        )


# Module-level singleton
_validator: LicenseValidator | None = None


def get_validator() -> LicenseValidator:
    """Get or create the license validator singleton."""
    global _validator
    if _validator is None:
        from backend.config import settings
        pub_key_path = getattr(settings, "license_public_key_path", "")
        if pub_key_path and Path(pub_key_path).exists():
            _validator = LicenseValidator(public_key_path=pub_key_path)
        else:
            # No public key configured — all license validation will fail gracefully
            _validator = LicenseValidator()
    return _validator
