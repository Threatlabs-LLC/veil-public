# Changelog

## v0.2.0 — Security, Polish & Hardening

### Audit & Observability
- Comprehensive audit logging across all security-relevant endpoints (auth, user management, settings, rules, policies, webhooks, API keys, conversations)
- Webhook event emission for auth failures, provider errors, and usage threshold hits
- Confirmation dialogs on all destructive actions (delete conversation, revoke key, remove user, delete webhook/rule/policy)

### Security Hardening
- Content Security Policy middleware (CSP, X-Content-Type-Options, X-Frame-Options, HSTS)
- Admin/owner role gating on settings and user management endpoints
- OAuth CSRF state validation with SHA-256 hashing and 10-min expiry
- CORS restricted to configured origins (no wildcard in production)
- Rate limiter exemptions for /auth/me, /auth/profile, OAuth endpoints

### Testing
- 486 tests across 10 files (485 pass, 1 pre-existing)
- Router coverage tests: conversations, api_keys, webhooks, models, settings
- Cross-org isolation tests, tier gating tests, SSRF validation tests

### Bug Fixes
- **Fixed SSE crash**: EntityBadge/EntityDiffView crash when `original` field is absent in streaming responses (null safety)
- Fixed silent error handlers — API failures now show error toasts instead of swallowing errors
- Fixed cloud-only code leak (subscription_status, Stripe migrations removed)
- Fixed outdated contact emails across codebase

### Feature Gating
- Per-feature enforcement: custom rules, webhooks, API keys, multi-provider, advanced audit
- Tier-based user limits with invite blocking
- Quota usage API (`GET /api/usage/quota`)

### Infrastructure
- Multi-worker uvicorn (`VEILCHAT_WORKERS` env var)
- `.dockerignore` for smaller Docker build context
- Rate limiter memory cleanup (stale key sweep)
- Configurable `VEILCHAT_APP_BASE_URL` (replaces hardcoded URLs for OAuth callbacks, password reset links)

### UI
- 404 page for invalid routes (was white screen)
- Error toasts/messages instead of silent failures (Admin, Settings, Webhooks)
- Confirmation dialogs for destructive actions (delete conversation, deactivate user)
- Clickable sidebar logo (navigate home)

### Documentation
- Updated DEPLOYMENT.md with `VEILCHAT_WORKERS` and `VEILCHAT_APP_BASE_URL` env vars
- Updated API.md with `/api/usage/quota` endpoint
- Fixed outdated contact emails in CODE_OF_CONDUCT.md

## v0.1.0 — Initial Release

### Core Features
- **PII Detection Engine**: 20+ regex patterns (SSN, credit card, email, IP, phone, AWS keys, connection strings, MAC addresses, hostnames, usernames, file paths, Windows domains, security log fields) + Presidio/spaCy NER (names, organizations, addresses) + custom org-specific rules
- **Reversible Pseudonymization**: Bidirectional entity-placeholder mapping scoped per conversation, with consistent placeholders (same entity always maps to same placeholder)
- **Policy Engine**: Per-entity-type actions (redact, block, warn, allow) with configurable priority, confidence thresholds, and severity levels
- **Streaming SSE Rehydration**: Real-time token streaming with chunk-boundary buffering for seamless placeholder replacement
- **3-Tier Overlap Resolution**: Custom rules > regex > NER priority system, with longest-span and highest-confidence tiebreakers
- **Security Log / SIEM Detection**: Specialized patterns for Palo Alto, CrowdStrike, and other security appliance log formats — usernames, hostnames, domain backslash notation, KV pairs

### API & Gateway
- **OpenAI-Compatible Gateway**: Drop-in `/v1/chat/completions` endpoint — change `base_url` and go
- **Sanitize API**: `POST /api/sanitize` and `POST /api/sanitize/batch` — detection-only endpoints for corpus testing, CI/CD integration, and benchmarking (no LLM call, no token cost)
- **Multi-Provider Support**: OpenAI, Anthropic, and Ollama (fully air-gapped local models)
- **REST API**: 30+ endpoints for chat, sanitize, conversations, rules, policies, admin, settings, webhooks, licensing
- **API Key Authentication**: Bcrypt-hashed keys with per-key rate limits

### Web UI
- Chat interface with real-time sanitization panel and entity diff view
- Admin dashboard with usage analytics, entity stats, and audit logs
- Settings page for API keys, provider configuration, Ollama URL
- Rules and policies management
- Webhook configuration
- User management and profiles
- Conversation search, sort, rename, export (JSON/Markdown)
- License management (activate/deactivate, tier badge)

### Infrastructure
- SQLite WAL (default) + PostgreSQL support
- Multi-stage Docker build with NER support (build arg)
- Docker Compose for production and development
- Kubernetes deployment manifests
- Caddy/Nginx reverse proxy configurations
- Structured JSON logging
- Health probes (`/live`, `/ready`) for Kubernetes
- Rate limiting middleware (sliding window)
- Event bus with webhook delivery

### Licensing
- Open-core model: Free tier with full features, paid tiers unlock higher limits
- RS256 JWT offline license validation (no phone-home)
- License key generator CLI
- Feature gating via FastAPI dependency injection
- Tier definitions: Free / Team / Business / Enterprise

### Testing & Quality
- 346 tests: detection quality (90), security (25), performance (15), API (50+), core engine, policy engine, rate limiting
- Detection benchmarks: <5ms regex, <500ms full pipeline with NER
- Security tests: SQL injection, XSS, PII leak prevention, auth enforcement
- Throughput: 500+ small msgs/sec, 100+ medium msgs/sec
- Tested against real-world Palo Alto firewall and CrowdStrike EDR log samples

### Detection Quality Improvements
- **Phone false positive reduction**: Requires formatting characters (parens, dashes, dots, spaces) — bare digit sequences no longer match as phone numbers
- **NER false positive reduction**: Max-length filters (PERSON 60 chars, ORG/LOCATION 100 chars), all-digit rejection for PERSON/ORG, removed UK_NHS entity type
- **Overlap resolution redesign**: 3-tier priority system (custom > regex > NER) prevents broad NER spans from eating precise regex matches
- **Security log patterns**: Username KV pairs (`user=`, `src_user=`, `domain=`), appliance hostnames, Windows domain\user notation, file paths
- **Seed data fix**: Built-in phone pattern now requires formatting to match (consistent with built-in detector)

### UI Polish
- **Sidebar polling**: Replaced 5-second interval with event-driven refresh (route change, window focus) + 30-second lazy fallback

### Documentation
- README with quick-start, architecture diagram, full API reference
- CONTRIBUTING.md, CODE_OF_CONDUCT.md
- Architecture guide (docs/ARCHITECTURE.md)
- Deployment guide (docs/DEPLOYMENT.md) — Docker, K8s, reverse proxy, env reference
- API reference (docs/API.md) — all endpoints with curl examples
- GitHub issue/PR templates

### CI/CD
- GitHub Actions CI: Python 3.11+3.12 matrix, frontend build, Docker push
- Release workflow: tag-triggered, ghcr.io push, auto-generated changelog
