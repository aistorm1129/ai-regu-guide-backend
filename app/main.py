from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.database import init_db
from app.api import auth, users, compliance, documents, dashboard, jurisdictions, tasks, reports, organizations, form_questions, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up...")
    # await init_db()  # Commented out since we use Alembic migrations
    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Configure CORS - Allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080", 
        "http://127.0.0.1:8080", 
        "http://localhost:3000",
        "https://ai-regu-guide-41.onrender.com",  # Production frontend
        settings.FRONTEND_URL  # From environment variable
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(jurisdictions.router, prefix="/api/jurisdictions", tags=["Jurisdictions"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(compliance.router, prefix="/api/compliance", tags=["Compliance"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(organizations.router, prefix="/api/organizations", tags=["Organizations"])
app.include_router(form_questions.router, prefix="/api/forms", tags=["Forms"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])


@app.get("/")
async def root():
    return {
        "message": "AI Compliance Guide API",
        "version": settings.VERSION,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# Simple test endpoints
@app.get("/test")
async def test():
    return {"message": "Backend is working", "cors": "enabled"}


@app.get("/api/test")
async def api_test():
    return {"message": "API endpoints are working", "timestamp": "2024-08-30"}