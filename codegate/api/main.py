import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from codegate.api.exceptions import register_exception_handlers
from codegate.api.routers import (
    analyses,
    analytics,
    auth,
    dashboard,
    findings,
    github,
    health,
    members,
    pull_requests,
    repositories,
    reviewer,
    system,
    testing,
    webhooks,
    workspaces,
)

app = FastAPI(
    title="CodeGate API",
    description="Pull Request Review & Quality Management Platform",
    version="0.1.0",
)

# CORS configuration
# Allow localhost for development. Production should use environment variables.
allow_origins = os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost,http://localhost:3000,http://localhost:5173,http://127.0.0.1,http://127.0.0.1:3000,http://127.0.0.1:5173")
origins = [origin.strip() for origin in allow_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health.router, prefix="/api/v1")
app.include_router(repositories.router, prefix="/api/v1")
app.include_router(pull_requests.router, prefix="/api/v1")
app.include_router(analyses.router, prefix="/api/v1")
app.include_router(findings.router, prefix="/api/v1")
app.include_router(testing.router, prefix="/api/v1")
app.include_router(reviewer.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(github.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(workspaces.router, prefix="/api/v1")
app.include_router(members.router)
app.include_router(webhooks.router)
