import logging
import time
from typing import Any, Dict

import httpx
import jwt
from fastapi import HTTPException

from codegate.config.settings import settings

logger = logging.getLogger(__name__)

class GitHubAppService:
    def __init__(self):
        self.app_id = settings.GITHUB_APP_ID
        self.private_key_path = settings.GITHUB_APP_PRIVATE_KEY_PATH
        self.app_slug = settings.GITHUB_APP_SLUG
        
    def _get_private_key(self) -> str:
        if not self.private_key_path:
            raise HTTPException(status_code=500, detail="GitHub App private key path is not configured.")
        try:
            with open(self.private_key_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="GitHub App private key file not found.")
        except Exception as e:
            logger.error(f"Error reading GitHub App private key: {e}")
            raise HTTPException(status_code=500, detail="Failed to read GitHub App private key.")

    def _generate_jwt(self) -> str:
        if not self.app_id:
            raise HTTPException(status_code=500, detail="GitHub App ID is not configured.")
            
        private_key = self._get_private_key()
        
        now = int(time.time())
        # JWT expiration time (8 minutes to safely tolerate local clock drift)
        payload = {
            "iat": now - 60,
            "exp": now + (8 * 60),
            "iss": self.app_id
        }
        
        try:
            encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")
            return encoded_jwt
        except Exception as e:
            logger.error(f"Failed to generate GitHub App JWT: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate GitHub App JWT.")

    async def get_installation(self, installation_id: str) -> Dict[str, Any]:
        """
        Fetch installation details from GitHub API using the App JWT.
        """
        app_jwt = self._generate_jwt()
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/app/installations/{installation_id}",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github.v3+json"
                },
                timeout=10.0
            )
            
            if response.status_code == 404:
                raise HTTPException(status_code=400, detail=f"Installation ID {installation_id} not found or inaccessible.")
            elif response.status_code != 200:
                logger.error(f"GitHub API Error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=502, detail="Failed to verify GitHub installation.")
                
            return response.json()

    async def get_installation_access_token(self, installation_id: str) -> str:
        """
        Exchange the App JWT for a short-lived Installation Access Token.
        """
        app_jwt = self._generate_jwt()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github.v3+json"
                },
                timeout=10.0
            )
            
            if response.status_code != 201:
                logger.error(f"GitHub Token API Error for {installation_id}: {response.status_code} - {response.text}")
                raise HTTPException(status_code=502, detail="Failed to acquire GitHub installation token.")
                
            data = response.json()
            return data["token"]

    async def get_installation_repositories(self, installation_token: str) -> list[Dict[str, Any]]:
        """
        Fetch all accessible repositories for this installation, handling pagination.
        """
        repos = []
        page = 1
        per_page = 100
        
        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(
                    "https://api.github.com/installation/repositories",
                    params={"per_page": per_page, "page": page},
                    headers={
                        "Authorization": f"Bearer {installation_token}",
                        "Accept": "application/vnd.github.v3+json"
                    },
                    timeout=20.0
                )
                
                if response.status_code != 200:
                    logger.error(f"GitHub Repositories API Error: {response.status_code} - {response.text}")
                    raise HTTPException(status_code=502, detail="Failed to fetch repositories from GitHub.")
                    
                data = response.json()
                current_repos = data.get("repositories", [])
                repos.extend(current_repos)
                
                if len(current_repos) < per_page:
                    break
                page += 1
                
        return repos
