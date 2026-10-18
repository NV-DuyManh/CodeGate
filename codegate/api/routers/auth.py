import hashlib
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from codegate.api.dependencies import get_current_user, get_db
from codegate.config.settings import settings
from codegate.database.models import AuthSession, User
from codegate.services.github_auth import get_github_access_token, get_github_user

router = APIRouter(prefix="/auth", tags=["auth"])

# State caching (in-memory for simplicity in Phase 7; in prod use redis or signed cookie)
# Using a signed cookie is better for statelessness
@router.get("/github/login")
async def github_login(response: Response):
    """
    Initiates GitHub OAuth flow.
    """
    if not settings.GITHUB_OAUTH_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GitHub OAuth is not configured")

    state = secrets.token_urlsafe(32)
    # Set state in a short-lived cookie for validation
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=settings.CODEGATE_COOKIE_SECURE,
        samesite="lax",
        max_age=300, # 5 minutes
    )

    params = {
        "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
        "redirect_uri": settings.GITHUB_OAUTH_CALLBACK_URL,
        "state": state,
        # "scope": "read:user user:email" # only basic identity needed
    }
    url = f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(params)}"
    
    # We must return a RedirectResponse, but also set the cookie.
    redirect = RedirectResponse(url)
    redirect.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=settings.CODEGATE_COOKIE_SECURE,
        samesite="lax",
        max_age=300,
    )
    return redirect


@router.get("/github/callback")
async def github_callback(
    code: str = None, 
    state: str = None, 
    oauth_state: str = Cookie(default=None),
    db: Session = Depends(get_db)
):
    """
    Handles the GitHub OAuth callback.
    """
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code missing")
    if not state or not oauth_state or state != oauth_state:
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state")
        
    if not settings.GITHUB_OAUTH_CLIENT_ID or not settings.GITHUB_OAUTH_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth is not configured")

    try:
        access_token = await get_github_access_token(
            client_id=settings.GITHUB_OAUTH_CLIENT_ID,
            client_secret=settings.GITHUB_OAUTH_CLIENT_SECRET,
            code=code,
            redirect_uri=settings.GITHUB_OAUTH_CALLBACK_URL
        )
        gh_user = await get_github_user(access_token)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth exchange failed: {str(e)}")

    # Find or create user
    user = db.scalar(
        select(User)
        .where(User.provider == "github")
        .where(User.provider_user_id == str(gh_user.id))
    )

    if not user:
        user = User(
            provider="github",
            provider_user_id=str(gh_user.id),
            username=gh_user.login,
            email=gh_user.email,
            avatar_url=gh_user.avatar_url,
            display_name=gh_user.name,
            is_active=True,
            last_login_at=datetime.now(timezone.utc)
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.username = gh_user.login
        user.email = gh_user.email or user.email
        user.avatar_url = gh_user.avatar_url or user.avatar_url
        user.last_login_at = datetime.now(timezone.utc)
        
    # Ensure active workspace is set if user has memberships
    if not user.active_workspace_id:
        from codegate.database.models import TeamMember
        first_member = db.scalar(
            select(TeamMember).where(TeamMember.user_id == user.id)
        )
        if first_member:
            user.active_workspace_id = first_member.team_id
            
    db.commit()

    # Create session
    session_token = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(session_token.encode()).hexdigest()
    
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.CODEGATE_SESSION_TTL_SECONDS)
    
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(auth_session)
    db.commit()

    # Create response and set cookie
    redirect_url = settings.CODEGATE_FRONTEND_URL.rstrip("/") + "/"
    response = RedirectResponse(redirect_url)
    
    response.set_cookie(
        key="codegate_session",
        value=session_token,
        httponly=True,
        secure=settings.CODEGATE_COOKIE_SECURE,
        samesite="lax",
        max_age=settings.CODEGATE_SESSION_TTL_SECONDS
    )
    # Clear oauth state
    response.delete_cookie("oauth_state")
    
    return response


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """
    Returns the currently authenticated user.
    """
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "active_workspace_id": user.active_workspace_id
    }


@router.post("/logout")
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Logs out the user by revoking the session and clearing the cookie.
    """
    session_token = request.cookies.get("codegate_session")
    if session_token:
        token_hash = hashlib.sha256(session_token.encode()).hexdigest()
        auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
        if auth_session:
            auth_session.revoked_at = datetime.now(timezone.utc)
            db.commit()
            
    response.delete_cookie("codegate_session")
    return {"status": "success"}
