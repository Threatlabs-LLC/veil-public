# Veil

[![CI](https://github.com/Threatlabs-LLC/veil-public/actions/workflows/ci.yml/badge.svg)](https://github.com/Threatlabs-LLC/veil-public/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue.svg)](https://github.com/Threatlabs-LLC/veil-public/pkgs/container/veilchat)

**Enterprise LLM sanitization proxy** — use any LLM at work with full data protection.

Veil sits between your users and LLM providers, automatically detecting and replacing sensitive data (PII, secrets, internal hostnames) with reversible placeholders before it ever reaches the model. Responses are rehydrated transparently, so users see the original data while the LLM never does.

```
User: "John Smith at john@acme.com called from 192.168.1.50"
  ↓ Veil detects & replaces
LLM:  "PERSON_001 at EMAIL_001 called from IP_ADDRESS_001"
  ↓ LLM responds with placeholders
User: "John Smith's email john@acme.com was confirmed"  ← rehydrated
```

## How to Use Veil

| | Free Self-Hosted | Cloud SaaS | Enterprise |
|---|:---:|:---:|:---:|
| **Get started** | `docker compose up` | [app.veilproxy.ai](https://app.veilproxy.ai) | Contact us |
| **Hosting** | Your infrastructure | Managed by Threatlabs | Your infrastructure |
| **Database** | SQLite (default) | PostgreSQL (managed) | PostgreSQL |
| **Support** | Community (GitHub) | Email + docs | Priority SLA |
| **Billing** | Free forever | Subscription | Annual license |

## Features

### Core (Free — no license required)

- **Automatic PII Detection** — 50+ regex patterns, NER (Presidio/spaCy), and custom dictionary rules
- **Reversible Pseudonymization** — bidirectional mapping tables, scoped per conversation
- **Policy Engine** — configurable per-entity actions: allow, redact, block, or warn
- **API Gateway Mode** — drop-in `base_url` replacement for existing OpenAI/Anthropic code
- **Web Chat UI** — built-in chat interface with real-time sanitization panel
- **Multi-Provider** — OpenAI, Anthropic, Ollama (local models)
- **Streaming SSE** — real-time token streaming with placeholder rehydration
- **Custom Rules** — add org-specific regex and dictionary detection patterns (up to 5)
- **Audit Trail** — full logging of every sanitization event (7-day retention)
- **User Management** — JWT auth, user profiles, up to 3 users
- **Document Scanner** — upload PDF, DOCX, TXT, CSV, XLSX files for PII scanning or chat context
- **Conversation Management** — search, sort, rename, export (JSON/CSV)
- **Admin Dashboard** — usage analytics, entity stats, audit logs
- **API Keys** — programmatic access with bcrypt-hashed keys
- **Health Probes** — `/api/health/live` and `/api/health/ready` for Kubernetes
- **Structured Logging** — JSON-formatted production logs
- **Rate Limiting** — configurable per-endpoint rate limits
- **Error Boundaries** — graceful error handling with toast notifications

### Paid Tiers

| Feature | Solo ($9/mo) | Team ($29/user/mo) | Business ($69/user/mo) | Enterprise |
|---------|:----:|:----:|:--------:|:----------:|
| Users | 1 | 25 | 200 | Unlimited |
| Custom rules | 10 | 100 | 500 | Unlimited |
| Webhooks / SIEM | 1 | 5 | 20 | 100 |
| Audit retention | 30 days | 90 days | 1 year | 2 years |
| Multi-provider | — | Yes | Yes | Yes |
| SSO (SAML/OIDC) | — | Yes | Yes | Yes |
| HIPAA compliance | — | — | Yes | Yes |
| Data residency | — | — | Yes | Yes |
| Custom NER models | — | — | — | Yes |
| Priority support | — | — | — | Yes |

> **Self-hosted licensing:** Same Docker image, same codebase. No license = Free tier. Drop a license key into Settings to unlock paid features. Offline validation — no phone-home.
>
> **Cloud:** Sign up at [app.veilproxy.ai](https://app.veilproxy.ai) and upgrade directly from the billing page. No license keys needed.

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────┐     ┌──────────┐
│  Web Chat   │     │              Veil Proxy                │     │  OpenAI  │
│     UI      │────▶│                                      │────▶│ Anthropic│
│             │◀────│  Detect → Policy → Sanitize → Forward │◀────│  Ollama  │
│  Settings   │     │  ◀── Rehydrate ◀── Stream response   │     │          │
│  Admin      │     │                                      │     │          │
└─────────────┘     │  ┌────────┐ ┌────────┐ ┌──────────┐ │     └──────────┘
                    │  │ Regex  │ │  NER   │ │ Custom   │ │
 ┌─────────────┐    │  │Detector│ │Presidio│ │  Rules   │ │
 │ Existing    │    │  └────────┘ └────────┘ └──────────┘ │
 │ Code        │    │                                      │
 │ (base_url)  │───▶│  /v1/chat/completions (gateway)     │
 └─────────────┘    └──────────────────────────────────────┘
                                   │
                             ┌─────┴─────┐
                             │  SQLite   │
                             │ (entities │
                             │  mappings │
                             │  audit)   │
                             └───────────┘
```

## Quick Start

> **Don't want to self-host?** Try [Veil Cloud](https://app.veilproxy.ai) — same features, fully managed.

### Prerequisites

- Python 3.11+
- Node.js 22+ (for frontend development)

### Install & Run

```bash
git clone https://github.com/Threatlabs-LLC/veil-public.git
cd veil-public

# Copy environment config
cp .env.example .env
# Edit .env with your API keys

# Install backend
pip install -e .

# Start the server
uvicorn backend.main:app --reload
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

### With Docker (recommended for production)

```bash
cp .env.example .env
# Edit .env with your API keys and a random secret key
docker compose up
```

Visit `http://localhost:8000` — register your first user, who becomes the org admin.

### Use the Gateway API

Point any OpenAI-compatible SDK at Veil — no code changes needed:

```python
from openai import OpenAI

# Just change the base_url — everything else stays the same
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="vk_your_veilchat_api_key"
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Review John Smith's config at 192.168.1.50"}]
)
# PII was sanitized before reaching OpenAI, then rehydrated in the response
print(response.choices[0].message.content)
```

Works with any tool that supports custom OpenAI base URLs: LangChain, LlamaIndex, Cursor, Continue, and more.

### Local Models with Ollama

Veil works fully air-gapped with Ollama — no cloud API keys needed:

```bash
# Start Ollama (separate process)
ollama serve
ollama pull llama3.2

# Veil auto-detects Ollama at localhost:11434
# Or configure a custom URL in Settings > Ollama Base URL
```

### Optional: NER Detection

For enhanced detection of names, organizations, and addresses:

```bash
pip install -e ".[ner]"
python -m spacy download en_core_web_md
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `POST /api/chat` | Chat with sanitization + SSE streaming |
| `POST /api/chat/with-document` | Chat with file attachment (multipart) |
| `POST /api/documents/scan` | Scan a document for PII (no LLM call) |
| `POST /api/sanitize` | Sanitize text without LLM call (detection only) |
| `POST /api/sanitize/batch` | Batch sanitize multiple texts |
| `POST /v1/chat/completions` | OpenAI-compatible gateway (drop-in) |
| `GET /api/models` | List available models by provider |
| `GET /api/admin/dashboard` | Dashboard stats |
| `GET /api/admin/usage` | Usage analytics (group by day/provider/model) |
| `GET /api/admin/audit` | Audit log queries |
| `GET/POST /api/rules` | Detection rules CRUD |
| `GET/POST /api/policies` | Policy management |
| `GET/PATCH /api/settings` | Org settings (API keys, defaults, Ollama URL) |
| `GET/POST/DELETE /api/webhooks` | Webhook management |
| `GET/POST/DELETE /api/api-keys` | API key management |
| `GET/POST /api/conversations` | Conversation list, search, export |
| `POST /api/auth/register` | User registration |
| `POST /api/auth/login` | JWT authentication |
| `GET /api/licensing/status` | Current license tier and features |
| `POST /api/licensing/activate` | Activate a license key |
| `GET /api/licensing/tiers` | List all tiers and features |
| `GET /api/health/live` | Liveness probe |
| `GET /api/health/ready` | Readiness probe |

## Detection Pipeline

Veil runs multiple detectors in parallel and merges results:

1. **Regex Detector** — 50+ patterns: IPs, emails, credit cards (with Luhn), SSNs, phones, AWS keys, connection strings, MAC addresses, internal hostnames, usernames, file paths, Windows domains, and security log/SIEM fields
2. **Presidio NER** — spaCy-backed named entity recognition for person names, organizations, addresses (optional)
3. **Custom Rules** — org-specific regex and dictionary patterns from the admin UI

Overlap resolution uses a 3-tier priority: custom rules > regex > NER. Within the same tier, longer spans win, then higher confidence.

## Policy Engine

Policies define what happens when PII is detected:

| Action | Behavior |
|---|---|
| `redact` | Replace with placeholder (default) |
| `block` | Reject the entire request |
| `warn` | Redact but flag for review |
| `allow` | Pass through unchanged |

Default policies block SSNs and credit cards, redact everything else. Fully configurable per entity type.

## Licensing

Veil uses an open-core model: the full-featured Free tier runs without any license. Paid tiers unlock higher limits and enterprise features.

**For self-hosted customers:**
```bash
# License key generator (business owner only — requires private key)
python -m backend.licensing.cli generate-keys --output-dir ./keys
python -m backend.licensing.cli create-license \
    --private-key ./keys/private_key.pem \
    --org-id "your-org-uuid" \
    --org-name "Acme Corp" \
    --tier team \
    --max-users 25 \
    --days 365
```

Licenses are RS256-signed JWTs validated offline with the public key. No internet connection required.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), SQLite WAL
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS, Lucide icons
- **Detection**: Regex + Presidio/spaCy NER + Custom rules
- **Auth**: JWT + API keys (bcrypt)
- **Streaming**: Server-Sent Events with chunk-boundary rehydration
- **Licensing**: RS256 JWT offline validation (PyJWT)
- **Containerization**: Multi-stage Docker build (Node + Python)

## Project Structure

```
veilchat/
├── backend/
│   ├── api/            # FastAPI endpoints
│   │   ├── chat.py         # Chat with sanitization + SSE
│   │   ├── gateway.py      # OpenAI-compatible /v1/chat/completions
│   │   ├── admin.py        # Dashboard, usage, audit, user management
│   │   ├── rules.py        # Detection rules CRUD
│   │   ├── policies.py     # Policy management
│   │   ├── settings.py     # Org settings (keys, providers, Ollama)
│   │   ├── webhooks.py     # Webhook CRUD
│   │   ├── api_keys.py     # API key management
│   │   ├── sanitize.py      # Detection-only API (no LLM call)
│   │   ├── conversations.py # Conversations, search, export
│   │   ├── models.py       # Dynamic model listing
│   │   ├── auth.py         # JWT auth, registration
│   │   └── licensing.py    # License activation/status
│   ├── core/           # Core logic
│   │   ├── sanitizer.py    # Multi-engine PII detection orchestrator
│   │   ├── rehydrator.py   # Streaming placeholder rehydration
│   │   ├── mapper.py       # Bidirectional entity ↔ placeholder mapping
│   │   ├── policy_engine.py # Per-entity policy evaluation
│   │   ├── audit.py        # Audit log writer
│   │   ├── events.py       # Event bus (webhooks, notifications)
│   │   ├── provider_keys.py # Provider API key resolution
│   │   ├── usage.py        # Usage tracking
│   │   ├── normalizer.py   # Text normalization
│   │   ├── document.py    # Document text extraction (PDF, DOCX, TXT, CSV, XLSX)
│   │   └── logging.py      # Structured JSON logging
│   ├── detectors/      # PII detection engines
│   │   ├── regex_detector.py    # 50+ regex patterns
│   │   ├── presidio_detector.py # spaCy NER (optional)
│   │   ├── custom_rule_detector.py # User-defined rules
│   │   └── registry.py         # Detector registration + overlap resolution
│   ├── licensing/      # License key system
│   │   ├── tiers.py        # Tier definitions and feature constants
│   │   ├── validator.py    # RS256 JWT validation
│   │   ├── dependencies.py # FastAPI dependency injection gates
│   │   └── cli.py          # Key generator CLI
│   ├── middleware/      # HTTP middleware
│   │   └── rate_limit.py   # Sliding-window rate limiter
│   ├── models/         # SQLAlchemy ORM (12 tables)
│   ├── providers/      # LLM providers
│   │   ├── openai_compat.py # OpenAI + Ollama (compatible API)
│   │   └── anthropic.py     # Anthropic Claude
│   ├── db/             # Database session, seeding
│   ├── tests/          # 442 tests
│   ├── config.py       # Environment config (Pydantic Settings)
│   └── main.py         # App entrypoint
├── frontend/
│   └── src/
│       ├── pages/          # Home, Chat, Admin, Settings, Login, Profile, Webhooks, Documents
│       ├── components/     # Sidebar, Layout, Chat UI, Sanitization panel, ErrorBoundary, Toast
│       ├── hooks/          # useChat custom hook
│       └── api/client.ts   # TypeScript API client
├── keys/               # License signing keys (private key gitignored)
├── docs/               # Architecture, API reference, deployment guide
├── Dockerfile          # Multi-stage build
├── docker-compose.yml  # Production-ready compose
├── Caddyfile           # Reverse proxy config
├── .env.example        # Full configuration reference
├── pyproject.toml      # Python dependencies
└── LICENSE             # MIT
```

## Configuration

All settings are configurable via environment variables. See [`.env.example`](.env.example) for the full reference.

Key variables:

| Variable | Default | Description |
|---|---|---|
| `VEILCHAT_OPENAI_API_KEY` | — | OpenAI API key |
| `VEILCHAT_ANTHROPIC_API_KEY` | — | Anthropic API key |
| `VEILCHAT_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama base URL |
| `VEILCHAT_SECRET_KEY` | `change-me...` | JWT signing secret |
| `VEILCHAT_DATABASE_URL` | SQLite | Database URL (supports PostgreSQL) |
| `VEILCHAT_LICENSE_PUBLIC_KEY_PATH` | — | Path to RS256 public key for license validation |

## Tests

```bash
# Run all tests (442 tests)
python -m pytest backend/tests/ -v

# Specific test modules
python -m pytest backend/tests/test_detection_quality.py -v    # 90 detection tests
python -m pytest backend/tests/test_accuracy_benchmark.py -v   # 76 accuracy benchmark tests
python -m pytest backend/tests/test_security.py -v             # 25 security tests
python -m pytest backend/tests/test_performance.py -v          # 15 performance benchmarks
python -m pytest backend/tests/test_api.py -v                  # API integration tests
python -m pytest backend/tests/test_core.py -v                 # Core engine tests
python -m pytest backend/tests/test_document.py -v             # Document extraction tests
```

## License

MIT License - see [LICENSE](LICENSE)

---

Built by [Threatlabs LLC](https://github.com/Threatlabs-LLC)
