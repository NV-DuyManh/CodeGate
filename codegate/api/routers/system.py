from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from codegate.api.dependencies import get_db
from codegate.database.models import GitHubConnection, Repository
from codegate.worker.celery_app import celery_app

router = APIRouter(prefix="/system", tags=["System"])

@router.get("/status")
def get_system_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    try:
        db.execute(text("SELECT 1")).scalar()
        db_status = "connected"
        engine_name = db.get_bind().dialect.name
    except Exception:
        db_status = "disconnected"
        engine_name = "unknown"
        
    # Check GitHub connection
    gh_conn = db.execute(select(GitHubConnection).where(GitHubConnection.status == "active")).scalars().first()
    
    if gh_conn:
        gh_status = "CONNECTED"
        account = f"@{gh_conn.account_login}"
        repo_count = db.scalar(select(func.count(Repository.id)).where(Repository.github_connection_id == gh_conn.id)) or 0
    else:
        gh_status = "NOT_CONFIGURED"
        account = None
        repo_count = 0
        
    # Check Celery and Redis
    try:
        i = celery_app.control.inspect(timeout=1.0)
        ping_res = i.ping()
        if ping_res is None:
            queue_status = "ONLINE"
            worker_status = "OFFLINE"
            connected_nodes = 0
        else:
            queue_status = "ONLINE"
            worker_status = "ONLINE"
            connected_nodes = len(ping_res)
    except Exception:
        queue_status = "OFFLINE"
        worker_status = "OFFLINE"
        connected_nodes = 0
        
    return {
        "status": "healthy",
        "database": {
            "status": db_status,
            "engine": engine_name
        },
        "data_mode": "LIVE" if gh_conn else "STANDALONE",
        "github": {
            "status": gh_status,
            "account": account,
            "repository_count": repo_count
        },
        "ai": {
            "status": "NOT_CONFIGURED",
            "provider": None
        },
        "webhook": {
            "status": "NOT_CONFIGURED"
        },
        "queue": {
            "status": queue_status
        },
        "worker": {
            "status": worker_status,
            "connected_nodes": connected_nodes
        },
        "test_runner": {
            "status": "DISABLED"
        },
        "version": "1.0.0"
    }
