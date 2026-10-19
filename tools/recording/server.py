"""Launch the existing API plus an explicitly local recording control router."""
import argparse
import asyncio
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


def _local_authority(value, is_origin=False):
    try:
        parsed = urlsplit(value if is_origin else f"//{value}")
        # Accessing port validates malformed/non-numeric/out-of-range ports.
        _ = parsed.port
        return (
            parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and (parsed.scheme in {"http", "https"} if is_origin else not parsed.scheme)
            and parsed.username is None and parsed.password is None
            and not parsed.path and not parsed.query and not parsed.fragment
        )
    except ValueError:
        return False


def local_only(request: Request):
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Recording controls are loopback-only")
    if not _local_authority(request.headers.get("host", "")):
        raise HTTPException(403, "Recording controls require a local Host header")
    origin = request.headers.get("origin")
    if origin and not _local_authority(origin, is_origin=True):
        raise HTTPException(403, "Recording controls accept local origins only")


def build_app(runtime_root):
    # Import after the CLI loads its dedicated database settings.
    from codegate.api.dependencies import get_db
    from codegate.api.main import app
    from codegate.database.base import Base
    from codegate.database.models import AnalysisRun, PullRequest, Repository
    from codegate.database.session import engine
    from tools.recording.harness import RecordingHarness

    Base.metadata.create_all(bind=engine)
    harness = RecordingHarness(runtime_root)
    lock = asyncio.Lock()

    router = APIRouter(prefix="/api/v1/recording", dependencies=[Depends(local_only)])

    @router.post("/session")
    def session(response: Response, db=Depends(get_db)):
        token, user = harness.create_session(db)
        response.set_cookie("codegate_session", token, httponly=True, samesite="lax", max_age=4 * 3600)
        return {"username": user.username, "workspace_id": user.active_workspace_id,
                "authentication": "Local recording session; GitHub OAuth is not configured"}

    @router.get("/status")
    def status(db=Depends(get_db)):
        user = harness.identity(db)
        runs = db.query(AnalysisRun).join(PullRequest).join(Repository).filter(
            Repository.workspace_id == user.active_workspace_id
        ).order_by(AnalysisRun.id.desc()).limit(10).all()
        return {"running": lock.locked(), "database": engine.dialect.name,
                "scope": "Real local source, analyzers, tests, coverage and persisted engine decisions",
                "integrations": {"ai": "NOT_CONFIGURED", "github_oauth": "NOT_CONFIGURED",
                                 "github_app": "NOT_CONFIGURED", "celery_queue": "NOT_USED"},
                "runs": [harness.evidence(db, item.id) for item in runs]}

    class AnalysisInput(BaseModel):
        case: Literal["unsafe", "safe"]

    @router.post("/analyze")
    async def analyze(payload: AnalysisInput, db=Depends(get_db)):
        if lock.locked():
            raise HTTPException(409, "A real recording analysis is already running")
        async with lock:
            return await harness.analyze(db, payload.case)

    @app.get("/recording", response_class=HTMLResponse, dependencies=[Depends(local_only)])
    def controls():
        return (Path(__file__).with_name("controls.html").read_text(encoding="utf-8")
                .replace("__DASHBOARD_URL__", os.environ.get("CODEGATE_FRONTEND_URL", "http://127.0.0.1:5173")))

    app.include_router(router)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--runtime-root", type=Path, default=Path(".runtime/recording"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    args.runtime_root.mkdir(parents=True, exist_ok=True)
    if args.env_file:
        from dotenv import load_dotenv
        if not args.env_file.is_file():
            parser.error("The explicit environment file does not exist")
        load_dotenv(args.env_file, override=True)
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{(args.runtime_root / 'recording.db').resolve().as_posix()}")
    import uvicorn
    uvicorn.run(build_app(args.runtime_root), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
