# TG-ENG-001 foundation status

Status: Initial source scaffold committed; build, tests, container startup, and dependency connectivity NOT YET VERIFIED.

## Stack
SvelteKit 5 / Svelte 5 frontend, FastAPI Python backend, PostgreSQL, Redis, Docker Compose. This is a modular-monolith starting point, not a production deployment.

## Local quick start
1. Copy `.env.example` to `.env` and replace the password.
2. Run `docker compose up --build`.
3. Check `http://localhost:3000`, `http://localhost:8000/health`, and `http://localhost:8000/ready`.
4. Run `PYTHONPATH=backend pytest -q backend/tests` after installing backend requirements, and `cd frontend && npm install && npm run check && npm test && npm run build`.

## Remaining gates
Confirm CI checks pass; confirm Compose services start and /ready works; pin dependencies/lockfile; introduce migrations, modular boundaries, secure configuration, operational observability and additional integration tests. Do not mark foundation complete until evidence exists.
