# VeilProxy

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL_1.1-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](Dockerfile)

**Enterprise LLM sanitization proxy** — use any AI model at work without leaking sensitive data.

VeilProxy sits between your users and LLM providers, automatically detecting and replacing PII, secrets, and internal data with reversible placeholders. The LLM never sees the real data. Responses are rehydrated transparently.

```
User: "John Smith at john@acme.com called from 192.168.1.50"
  ↓ VeilProxy detects & replaces
LLM:  "PERSON_001 at EMAIL_001 called from IP_ADDRESS_001"
  ↓ LLM responds with placeholders
User: "John Smith's email john@acme.com was confirmed"  ← rehydrated
```

<!-- TODO: Add screenshot of chat UI with sanitization panel -->

## Quick Start

```bash
git clone https://github.com/Threatlabs-LLC/veil-public.git
cd veil-public
cp .env.example .env    # Add your API keys
docker compose up
```

Visit `http://localhost:8000` — register your first user (becomes org admin).

> **Don't want to self-host?** Try [VeilProxy Cloud](https://app.veilproxy.ai) — same features, fully managed.

## Gateway API

Drop VeilProxy into existing code — just change the `base_url`:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="vk_your_api_key"
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Review John Smith's config at 192.168.1.50"}]
)
# PII was sanitized before reaching OpenAI, response was rehydrated
print(response.choices[0].message.content)
```

Works with LangChain, LlamaIndex, Cursor, Continue, and any OpenAI-compatible client.

## Features

- **PII Detection** — regex patterns, NER (Presidio/spaCy), and custom dictionary rules
- **Reversible Pseudonymization** — bidirectional mapping, scoped per conversation
- **Policy Engine** — per-entity actions: allow, redact, block, or warn
- **Multi-Provider** — OpenAI, Anthropic, Ollama (fully air-gapped)
- **Streaming** — SSE with real-time placeholder rehydration
- **Web Chat UI** — built-in chat interface with live sanitization panel
- **Document Scanner** — scan PDF, DOCX, TXT, CSV, XLSX for PII
- **Admin Dashboard** — usage analytics, audit logs, user management
- **API Keys & Webhooks** — programmatic access and event integrations
- **Google OAuth** — "Continue with Google" login (configurable)
- **Password Reset** — SMTP-based email reset flow with branded templates
- **Health Probes** — `/api/health/live` and `/api/health/ready` for Kubernetes

<!-- TODO: Add screenshot of admin dashboard -->

## Local Models (Air-Gapped)

```bash
ollama serve && ollama pull llama3.2
# VeilProxy auto-detects Ollama at localhost:11434
```

## Configuration

All settings via environment variables with `VEILCHAT_` prefix. See [`.env.example`](.env.example) for the full reference.

| Variable | Description |
|---|---|
| `VEILCHAT_OPENAI_API_KEY` | OpenAI API key |
| `VEILCHAT_ANTHROPIC_API_KEY` | Anthropic API key |
| `VEILCHAT_OLLAMA_BASE_URL` | Ollama URL (default: `localhost:11434/v1`) |
| `VEILCHAT_SECRET_KEY` | JWT signing secret (required in production) |
| `VEILCHAT_DATABASE_URL` | Database URL (default: SQLite, supports PostgreSQL) |
| `VEILCHAT_GOOGLE_CLIENT_ID` | Google OAuth client ID (optional) |
| `VEILCHAT_GOOGLE_CLIENT_SECRET` | Google OAuth client secret (optional) |
| `VEILCHAT_SMTP_HOST` | SMTP server for password reset emails (optional) |
| `VEILCHAT_SMTP_FROM_EMAIL` | From address for emails (optional) |

## Licensing

Open-core model — Free tier runs without any license key. Paid tiers unlock higher limits and enterprise features (more users, custom rules, webhooks, SSO, compliance).

See [veilproxy.ai](https://veilproxy.ai) for pricing and tier details.

## Docs

- [API Reference](https://veilproxy.ai/docs/) — full endpoint documentation
- [Deployment Guide](https://veilproxy.ai/deploy/) — Docker, Kubernetes, reverse proxy configs
- [`.env.example`](.env.example) — all configuration options

## Tech Stack

Python 3.12 · FastAPI · SQLAlchemy (async) · React 19 · TypeScript · Vite · Tailwind CSS

## License

BSL 1.1 — see [LICENSE](LICENSE). Self-hosting for internal use is always permitted. Converts to Apache 2.0 on Feb 20, 2030.

---

Built by [Threatlabs LLC](https://github.com/Threatlabs-LLC) · [veilproxy.ai](https://veilproxy.ai)
