"""License key generator CLI.

This tool is for the VeilChat business owner ONLY.
It generates signed license JWTs using the PRIVATE key.
The private key should NEVER be in the Docker image or public repo.

Usage:
    # Generate RSA keypair (one-time setup):
    python -m backend.licensing.cli generate-keys --output-dir ./keys

    # Generate a license key for a customer:
    python -m backend.licensing.cli create-license \
        --private-key ./keys/private_key.pem \
        --org-id "550e8400-e29b-41d4-a716-446655440000" \
        --org-name "Acme Corp" \
        --tier team \
        --max-users 25 \
        --days 365

    # Inspect a license key:
    python -m backend.licensing.cli inspect --token "eyJ..."
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path


def generate_keys(output_dir: str) -> None:
    """Generate RS256 keypair for license signing."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        print("Error: cryptography package required. Install with: pip install cryptography")
        sys.exit(1)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Write private key
    private_path = out / "private_key.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    # Write public key
    public_path = out / "public_key.pem"
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    print(f"Keys generated:")
    print(f"  Private key: {private_path}  (KEEP SECRET — never commit or ship)")
    print(f"  Public key:  {public_path}  (safe to distribute with Docker image)")


def create_license(
    private_key_path: str,
    org_id: str,
    org_name: str,
    tier: str,
    max_users: int,
    days: int,
) -> str:
    """Generate a signed license JWT."""
    try:
        import jwt as pyjwt
    except ImportError:
        print("Error: PyJWT[crypto] required. Install with: pip install PyJWT[crypto]")
        sys.exit(1)

    from backend.licensing.tiers import TIERS, get_tier

    if tier not in TIERS:
        print(f"Error: Unknown tier '{tier}'. Valid: {', '.join(TIERS.keys())}")
        sys.exit(1)

    tier_def = get_tier(tier)
    private_key = Path(private_key_path).read_text()
    now = int(time.time())

    payload = {
        "sub": org_id,
        "org_name": org_name,
        "tier": tier,
        "max_users": max_users,
        "features": sorted(tier_def.features),
        "iss": "VeilChat License Authority",
        "iat": now,
        "exp": now + (days * 86400),
        "jti": str(uuid.uuid4()),
    }

    token = pyjwt.encode(payload, private_key, algorithm="RS256")
    return token


def inspect_token(token: str) -> None:
    """Decode and display license claims (no signature verification)."""
    try:
        import jwt as pyjwt
        claims = pyjwt.decode(token, options={"verify_signature": False})
    except ImportError:
        # Manual base64 decode
        import base64
        parts = token.split(".")
        if len(parts) != 3:
            print("Error: Not a valid JWT")
            sys.exit(1)
        payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))

    print(json.dumps(claims, indent=2))

    exp = claims.get("exp", 0)
    if exp:
        remaining = (exp - time.time()) / 86400
        if remaining > 0:
            print(f"\nStatus: VALID ({int(remaining)} days remaining)")
        else:
            print(f"\nStatus: EXPIRED ({int(-remaining)} days ago)")


def main():
    parser = argparse.ArgumentParser(description="VeilChat License Manager")
    sub = parser.add_subparsers(dest="command")

    # generate-keys
    keygen = sub.add_parser("generate-keys", help="Generate RS256 keypair")
    keygen.add_argument("--output-dir", default="./keys", help="Output directory")

    # create-license
    create = sub.add_parser("create-license", help="Generate a signed license key")
    create.add_argument("--private-key", required=True, help="Path to private_key.pem")
    create.add_argument("--org-id", required=True, help="Organization UUID")
    create.add_argument("--org-name", required=True, help="Organization name")
    create.add_argument("--tier", required=True, choices=["free", "team", "business", "enterprise"])
    create.add_argument("--max-users", type=int, default=25, help="Max users (default: 25)")
    create.add_argument("--days", type=int, default=365, help="Validity in days (default: 365)")

    # inspect
    insp = sub.add_parser("inspect", help="Decode and display a license key")
    insp.add_argument("--token", required=True, help="JWT license token")

    args = parser.parse_args()

    if args.command == "generate-keys":
        generate_keys(args.output_dir)
    elif args.command == "create-license":
        token = create_license(
            args.private_key, args.org_id, args.org_name,
            args.tier, args.max_users, args.days,
        )
        print(token)
    elif args.command == "inspect":
        inspect_token(args.token)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
