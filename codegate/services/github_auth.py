from typing import Optional

import httpx
from fastapi import HTTPException
from pydantic import BaseModel


class GitHubUser(BaseModel):
    id: int
    login: str
    avatar_url: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None


async def get_github_access_token(client_id: str, client_secret: str, code: str, redirect_uri: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri
            },
            timeout=10.0
        )
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve GitHub access token")
            
        data = response.json()
        if "error" in data:
            raise HTTPException(status_code=400, detail=f"GitHub OAuth Error: {data['error_description']}")
            
        return data["access_token"]


async def get_github_user(access_token: str) -> GitHubUser:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json"
            },
            timeout=10.0
        )
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Failed to fetch GitHub user profile")
            
        return GitHubUser(**response.json())
