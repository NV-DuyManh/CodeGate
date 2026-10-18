import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from codegate.api.dependencies import get_db
from codegate.config.settings import settings as cg_settings
from codegate.database.models.analysis import AnalysisJob, AnalysisRun, Status, Trigger
from codegate.database.models.github import GitHubConnection
from codegate.database.models.repository import Repository
from codegate.database.models.webhook import WebhookEvent
from codegate.services.github_sync_service import GithubSyncService
from codegate.worker.tasks import analyze_pull_request
from pr_agent.config_loader import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/github_webhooks", tags=["webhooks"])

def verify_signature(body: bytes, secret: str, signature: str):
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")
    
    hash_object = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


async def process_webhook_synchronously(db: Session, delivery_id: str, event_type: str, action: str, body: dict, webhook_event: WebhookEvent):
    """
    Processes the webhook event synchronously, enqueuing background tasks if needed.
    """
    try:
        if event_type == "pull_request":
            if action in ["opened", "synchronize", "reopened", "closed"]:
                pr_url = body.get("pull_request", {}).get("html_url")
                if not pr_url:
                    raise ValueError("No PR URL found in payload")
                
                installation_id = str(body.get("installation", {}).get("id", ""))
                if not installation_id:
                    raise ValueError("No installation ID found in payload")

                # Verify connection exists for this installation
                connection = db.query(GitHubConnection).filter_by(installation_id=installation_id).first()
                if not connection:
                    raise ValueError(f"No active GitHubConnection found for installation {installation_id}")
                
                get_settings().set("GITHUB.DEPLOYMENT_TYPE", "app")
                get_settings().set("GITHUB.APP_ID", cg_settings.GITHUB_APP_ID)
                if cg_settings.GITHUB_APP_PRIVATE_KEY_PATH:
                    with open(cg_settings.GITHUB_APP_PRIVATE_KEY_PATH, 'r') as f:
                        get_settings().set("GITHUB.PRIVATE_KEY", f.read())
                
                get_settings().set("GITHUB.INSTALLATION_ID", int(installation_id))
                
                # 1. Sync Data (Upsert Repo and PR)
                sync_service = GithubSyncService(db)
                repo, pr = sync_service.sync_pull_request(pr_url)
                
                # 2. Trigger Analysis if needed
                if action in ["opened", "synchronize"]:
                    # Create AnalysisRun
                    run = AnalysisRun(
                        pull_request_id=pr.id,
                        head_sha=pr.head_sha,
                        status=Status.QUEUED,
                        trigger=Trigger.WEBHOOK
                    )
                    db.add(run)
                    db.commit()
                    db.refresh(run)

                    # Create AnalysisJob for Celery
                    job = AnalysisJob(
                        analysis_run_id=run.id,
                        status="QUEUED",
                        queued_at=datetime.now(timezone.utc)
                    )
                    db.add(job)
                    db.commit()

                    # Enqueue Celery task
                    try:
                        analyze_pull_request.delay(run.id)
                    except Exception as e:
                        logger.error(f"Failed to enqueue celery task for run {run.id}: {e}")
                        # We don't fail the webhook, but we update the job state if possible
                        job.status = "FAILED"
                        job.last_error = f"Enqueue failed: {str(e)}"
                        run.status = Status.FAILED
                        run.error_message = job.last_error
                        db.commit()

        elif event_type == "installation_repositories":
            installation_id = str(body.get("installation", {}).get("id"))
            connection = db.query(GitHubConnection).filter_by(installation_id=installation_id).first()
            if connection:
                sync_service = GithubSyncService(db)
                await sync_service.sync_repositories(connection.id)
                
        elif event_type == "installation":
            if action in ["deleted", "suspend"]:
                installation_id = str(body.get("installation", {}).get("id"))
                connection = db.query(GitHubConnection).filter_by(installation_id=installation_id).first()
                if connection:
                    connection.status = "DISCONNECTED" if action == "deleted" else "SUSPENDED"
                    
                    repos = db.query(Repository).filter_by(github_connection_id=connection.id).all()
                    now = datetime.now(timezone.utc)
                    for repo in repos:
                        repo.access_status = "ACCESS_REMOVED"
                        repo.last_synced_at = now
                    db.commit()
                    
        webhook_event.status = "PROCESSED"
        webhook_event.processed_at = datetime.now(timezone.utc)
        db.commit()
        
    except Exception as e:
        logger.exception("Failed to process webhook event")
        webhook_event.status = "FAILED"
        webhook_event.error_message = str(e)
        webhook_event.processed_at = datetime.now(timezone.utc)
        db.commit()


@router.post("")
async def handle_github_webhooks(
    request: Request, 
    db: Session = Depends(get_db)
):
    body_bytes = await request.body()
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error parsing JSON")

    webhook_secret = cg_settings.GITHUB_WEBHOOK_SECRET
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="GitHub webhook verification is not configured")
    signature_header = request.headers.get('x-hub-signature-256', None)
    verify_signature(body_bytes, webhook_secret, signature_header)

    event_type = request.headers.get("X-GitHub-Event", "unknown")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    
    if not delivery_id:
        return {"status": "ignored", "reason": "No delivery id"}

    existing = db.query(WebhookEvent).filter_by(provider="github", delivery_id=delivery_id).first()
    if existing:
        return {"status": "ignored", "reason": "Duplicate event"}

    action = body.get("action", "unknown")
    repo_full_name = body.get("repository", {}).get("full_name")
    pr_number = body.get("pull_request", {}).get("number")
    payload_hash = hashlib.sha256(body_bytes).hexdigest()

    webhook_event = WebhookEvent(
        provider="github",
        delivery_id=delivery_id,
        event_type=event_type,
        action=action,
        repository_full_name=repo_full_name,
        pull_request_number=pr_number,
        payload_hash=payload_hash,
        status="PENDING"
    )
    db.add(webhook_event)
    db.commit()

    # Process immediately and return 202
    await process_webhook_synchronously(db, delivery_id, event_type, action, body, webhook_event)
    
    return Response(content=json.dumps({"status": "accepted"}), status_code=202, media_type="application/json")
