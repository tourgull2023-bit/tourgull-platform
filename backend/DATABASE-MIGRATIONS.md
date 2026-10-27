# TG-ENG-001.7 — Database migrations

Use the existing PostgreSQL service and `DATABASE_URL`. Never commit `.env` or production credentials.

From the repository root, with backend dependencies installed and `DATABASE_URL` configured:

```sh
alembic -c backend/alembic.ini upgrade head
alembic -c backend/alembic.ini current
```

The first revision creates only `platform_settings` and Alembic's version table. No commercial module tables or customer data are created. Do not run `downgrade` on production databases without a reviewed backup and rollback plan. CI tests the migration against an ephemeral PostgreSQL instance. Production rollout, secrets, backups, and permissions remain separate acceptance gates.
