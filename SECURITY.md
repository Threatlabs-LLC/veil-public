# Security Policy

## Reporting a Vulnerability

**Please do NOT open public GitHub issues for security vulnerabilities.**

If you discover a security issue in VeilProxy, email us at:

**security@veilproxy.ai**

Include:
- Description of the vulnerability
- Steps to reproduce
- Affected version(s)
- Impact assessment (if known)
- Suggested fix (optional)

We will acknowledge receipt within **48 hours** and provide status updates as we investigate. Critical issues are prioritized and patched as quickly as possible.

## Supported Versions

| Version | Status |
|---------|--------|
| 0.3.x   | Active support, security patches |
| < 0.3   | End of life, no patches |

## Security Measures

VeilProxy is built with security as a core design principle:

- **No PII storage by default** — sanitized text is processed in-memory, not persisted
- **JWT authentication** with bcrypt password hashing
- **Rate limiting** — tier-aware, with brute-force protection on auth endpoints
- **Security headers** — CSP, HSTS, X-Frame-Options, X-Content-Type-Options
- **Input validation** — Pydantic v2 models on all API endpoints
- **SQL injection protection** — SQLAlchemy ORM with parameterized queries
- **Path traversal protection** — validated file access in document scanning
- **Audit logging** — all sensitive operations logged with timestamps and user context

## Disclosure Timeline

1. **Day 0** — Report received, acknowledgment sent
2. **Day 1–7** — Triage and impact assessment
3. **Day 7–30** — Patch development and testing
4. **Day 30** — Patch released, advisory published
5. **Day 90** — Full disclosure (coordinated with reporter)

We follow responsible disclosure practices and will credit reporters in our security advisories unless anonymity is requested.

## Bug Bounty

We do not currently operate a formal bug bounty program. However, we recognize and credit security researchers who responsibly disclose vulnerabilities.

## Contact

- Security reports: security@veilproxy.ai
- General support: support@veilproxy.ai
- GitHub: [github.com/Threatlabs-LLC/veil-public](https://github.com/Threatlabs-LLC/veil-public)
