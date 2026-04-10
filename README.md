# Extravis Partner Portal

A full-stack web application for managing partner onboarding, opportunities, deal registration, document workflows, training (LMS), and a knowledge base for Extravis and its partner ecosystem.

## Tech Stack

**Backend**
- FastAPI (Python)
- PostgreSQL 15 (async via SQLAlchemy + asyncpg)
- Alembic migrations
- Redis 7 (cache / sessions)
- JWT authentication

**Frontend**
- React 18 + TypeScript
- Vite 6
- Ant Design 5 + `@ant-design/charts`
- React Router 6
- TanStack Query
- Axios

**Infrastructure**
- Docker Compose (db, redis, backend, frontend, nginx)
- Nginx reverse proxy

## Project Structure

```
partner_portal/
├── backend/                  # FastAPI service
│   ├── app/
│   │   ├── api/v1/endpoints/ # auth, partners, companies, opportunities,
│   │   │                     # doc_requests, knowledge_base, lms,
│   │   │                     # notifications, onboarding, dashboard,
│   │   │                     # audit_logs, bulk_import
│   │   ├── core/             # config, security, db, init
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # business logic
│   │   ├── templates/        # email templates
│   │   └── utils/
│   ├── alembic/              # database migrations
│   ├── uploads/              # file uploads (gitignored)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # React + Vite SPA
│   ├── src/
│   │   ├── api/              # axios clients
│   │   ├── components/
│   │   ├── contexts/
│   │   ├── hooks/
│   │   ├── pages/            # auth, dashboard, partners, companies,
│   │   │                     # opportunities, deals, documents,
│   │   │                     # knowledge-base, lms, notifications,
│   │   │                     # users, profile
│   │   ├── styles/
│   │   ├── types/
│   │   └── utils/
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.ts
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
├── .env.example
└── Extravis_Partner_Portal_SRS_v1.0.docx
```

## Features

- **Authentication & Authorization** — JWT access/refresh tokens, password reset, account activation, login rate limiting & lockout
- **Partner Onboarding** — multi-step onboarding workflow with document collection
- **Companies & Partners** — directory and lifecycle management
- **Opportunities & Deal Registration** — pipeline tracking
- **Document Requests** — request, upload, and review documents
- **Knowledge Base** — searchable internal knowledge repository
- **LMS** — training modules for partner enablement
- **Notifications** — in-app and email notifications
- **Bulk Import** — CSV/Excel ingest for partner data
- **Audit Logs** — full action audit trail
- **Dashboard** — KPIs and charts for portal activity

## Quick Start (Docker)

The fastest way to get everything running:

```bash
# 1. Copy and edit environment variables
cp .env.example .env
# Edit .env: set JWT_SECRET_KEY, SMTP credentials, SUPERADMIN_PASSWORD, etc.

# 2. Build and start all services
docker compose up --build
```

Services will be available at:

| Service   | URL                       |
|-----------|---------------------------|
| Frontend  | http://localhost:5173     |
| Backend   | http://localhost:8001     |
| API docs  | http://localhost:8001/docs |
| Nginx     | http://localhost           |
| Postgres  | localhost:5432            |
| Redis     | localhost:6379            |

The backend container automatically runs `alembic upgrade head` and bootstraps the superadmin account on startup.

## Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Make sure Postgres and Redis are running and DATABASE_URL / REDIS_URL
# in your .env point to them.

alembic upgrade head
python -m app.core.init_db
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite will serve the app at http://localhost:5173 with HMR.

## Environment Variables

See [`.env.example`](./.env.example) for the full list. Key variables:

- `DATABASE_URL` — async Postgres connection string
- `REDIS_URL`
- `JWT_SECRET_KEY` — must be a strong random string (≥ 32 chars)
- `SMTP_*` — outbound email (SendGrid by default)
- `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` — bootstrap admin account
- `CORS_ORIGINS` — JSON array of allowed origins
- `FRONTEND_URL` — used in email links

## Database Migrations

```bash
cd backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## API Documentation

Once the backend is running, interactive Swagger docs are available at:

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

## License

Proprietary — © Extravis. All rights reserved.
