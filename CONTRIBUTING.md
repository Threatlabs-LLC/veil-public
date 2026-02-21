# Contributing to Veil

Thanks for your interest in contributing to Veil! This guide covers how to set up a development environment, run tests, and submit changes.

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 22+
- Git

### 1. Clone and install

```bash
git clone https://github.com/Threatlabs-LLC/veil-public.git
cd veil-public

# Backend
pip install -e ".[dev]"

# Optional: NER support (Presidio + spaCy)
pip install -e ".[ner]"
python -m spacy download en_core_web_md

# Frontend
cd frontend && npm install && cd ..
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set VEILCHAT_SECRET_KEY to a random string
```

### 3. Start development servers

```bash
# Terminal 1: Backend (auto-reload)
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend (Vite dev server)
cd frontend && npm run dev
```

Or use Docker:

```bash
docker compose -f docker-compose.dev.yml up
```

### 4. Open the app

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000/docs (Swagger UI)

## Running Tests

```bash
# All tests
python -m pytest backend/tests/ -v

# Specific test file
python -m pytest backend/tests/test_detection_quality.py -v

# With coverage (if installed)
python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

### Frontend type checking

```bash
cd frontend
npx tsc --noEmit
npm run build
```

## Code Style

### Python

- We use [Ruff](https://docs.astral.sh/ruff/) for linting
- Line length: 100 characters
- Target: Python 3.12+

```bash
ruff check backend/ --select E,F,W --ignore E402,E501
```

### TypeScript

- Standard TypeScript strict mode
- Functional React components with hooks
- Tailwind CSS for styling

## Making Changes

### Branch naming

- `feature/short-description` — new features
- `fix/short-description` — bug fixes
- `docs/short-description` — documentation changes

### Commit messages

Use clear, imperative-mood commit messages:

```
Add SSN detection for hyphenated format
Fix rate limiter not resetting after window expires
Update deployment docs with Kubernetes example
```

### Pull request process

1. Fork the repository and create a branch from `master`
2. Make your changes and add tests for new functionality
3. Run the full test suite and ensure it passes
4. Update documentation if your change affects user-facing behavior
5. Submit a pull request with a clear description of the changes

### What makes a good PR

- **Focused**: One logical change per PR
- **Tested**: New features have tests, bug fixes have regression tests
- **Documented**: User-facing changes update relevant docs
- **Small**: Easier to review — split large changes into multiple PRs

## Adding a New PII Detector

Veil's detection system is modular. To add a new entity type:

1. Add regex patterns to `backend/detectors/regex_detector.py`
2. Add test cases to `backend/tests/test_detection_quality.py`
3. Add a default policy in `backend/db/seed.py`
4. Update the entity type list in the README

## Reporting Issues

- Use the GitHub issue templates (bug report or feature request)
- Include reproduction steps for bugs
- Include your Python version, OS, and whether NER is installed

## License

By contributing, you agree that your contributions will be licensed under the BSL 1.1 License.
