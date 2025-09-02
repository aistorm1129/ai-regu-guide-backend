# AI Compliance Guide - Backend API

FastAPI backend for the AI Compliance Management application.

## Setup Instructions

### 1. Prerequisites

- Python 3.9+
- PostgreSQL 13+
- Google OAuth credentials (for social login)

### 2. Database Setup

Create a PostgreSQL database:
```sql
CREATE DATABASE ai_compliance_db;
```

### 3. Environment Configuration

Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

Update the following in `.env`:
- `DATABASE_URL` - Your PostgreSQL connection string
- `SECRET_KEY` - Generate a secure secret key
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` - From Google Cloud Console

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Run Database Migrations

Initialize Alembic (first time only):
```bash
alembic init alembic
```

Create initial migration:
```bash
alembic revision --autogenerate -m "Initial migration"
```

Apply migrations:
```bash
alembic upgrade head
```

### 6. Start Development Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`
API documentation at `http://localhost:8000/docs`

## API Documentation

### Authentication Endpoints

- `POST /auth/register` - Register new user
- `POST /auth/login` - Login with email/password
- `GET /auth/google` - Get Google OAuth URL
- `POST /auth/google` - Handle Google OAuth callback
- `POST /auth/refresh` - Refresh access token
- `POST /auth/logout` - Logout user

### Protected Endpoints

All `/api/*` endpoints require authentication via JWT token in the Authorization header:
```
Authorization: Bearer <access_token>
```

## Testing

Run tests with:
```bash
pytest
```

## Production Deployment

For production, use:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Or deploy with Docker:
```bash
docker build -t ai-compliance-backend .
docker run -p 8000:8000 --env-file .env ai-compliance-backend
```