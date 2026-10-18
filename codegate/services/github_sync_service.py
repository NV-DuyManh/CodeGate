import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from codegate.database.models.github import GitHubConnection
from codegate.database.models.pull_request import PullRequest
from codegate.database.models.repository import Repository
from codegate.services.github_app import GitHubAppService
from codegate.services.pr_service import PullRequestService
from codegate.services.repository_service import RepositoryService
from pr_agent.git_providers import get_git_provider_with_context

logger = logging.getLogger(__name__)


class GithubSyncService:
    """
    Synchronizes a GitHub PR (via PR-Agent's GithubProvider) into the CodeGate database.
    """
    def __init__(self, db: Session):
        self.db = db
        self.repo_service = RepositoryService()
        self.pr_service = PullRequestService()

    def sync_pull_request(self, pr_url: str) -> Tuple[Repository, PullRequest]:
        """
        Uses PR-Agent's provider to fetch the PR, then upserts the Repository and PullRequest
        into the CodeGate DB.
        """
        # Note: If no token is configured, this will throw an exception.
        # But this is exactly what we want (it requires the system to be configured correctly).
        provider = get_git_provider_with_context(pr_url)
        
        if not getattr(provider, "pr", None):
            raise ValueError(f"Provider failed to load a PR object for {pr_url}")
            
        pr_obj = provider.pr
        repo_obj = getattr(provider, "repo", None)

        if not repo_obj and hasattr(pr_obj, "base") and hasattr(pr_obj.base, "repo"):
            repo_obj = pr_obj.base.repo

        # Extract Repository Data
        # If repo_obj doesn't have full_name, extract from URL
        repo_full_name = getattr(repo_obj, "full_name", "")
        if not repo_full_name:
            # pr_url e.g. https://github.com/owner/repo/pull/1
            parts = pr_url.rstrip("/").split("/")
            if len(parts) >= 6:
                repo_full_name = f"{parts[-4]}/{parts[-3]}"
        if not repo_full_name:
            repo_full_name = pr_url.split("github.com/")[-1].split("/pull")[0]

        repo_url = f"https://github.com/{repo_full_name}"
        
        # 1. Upsert Repository
        from codegate.repositories.repo_store import repo_store
        # We need to find it by full_name
        repository = repo_store.get_by_full_name(self.db, "GITHUB", repo_full_name)
        if not repository:
            # We bypass the pydantic schema for internal sync since we have direct models
            owner_name = repo_full_name.split("/")[0] if "/" in repo_full_name else ""
            repo_name = repo_full_name.split("/")[-1]
            repository = Repository(
                name=repo_name,
                owner=owner_name,
                full_name=repo_full_name,
                provider="GITHUB",
                url=repo_url,
                active=True,
                data_source="LIVE"
            )
            self.db.add(repository)
            self.db.commit()
            self.db.refresh(repository)

        # Extract PR Data
        pr_number = getattr(provider, "pr_num", None)
        if not pr_number and hasattr(pr_obj, "number"):
            pr_number = pr_obj.number
        
        title = provider.get_title()
        description = getattr(pr_obj, "body", "") or ""
        author = getattr(pr_obj.user, "login", "") if hasattr(pr_obj, "user") else ""
        
        target_branch = provider.get_pr_branch()
        # Head branch is sometimes tricky, let's grab it from the provider if possible
        source_branch = getattr(pr_obj.head, "ref", "") if hasattr(pr_obj, "head") else ""
        head_sha = getattr(pr_obj.head, "sha", "") if hasattr(pr_obj, "head") else ""
        base_sha = getattr(pr_obj.base, "sha", "") if hasattr(pr_obj, "base") else ""
        
        state = getattr(pr_obj, "state", "OPEN").upper()
        if getattr(pr_obj, "merged", False):
            state = "MERGED"

        changed_files_list = provider.get_diff_files() or []
        changed_files_count = len(changed_files_list)

        # 2. Upsert PullRequest
        # Check if PR exists
        pull_request = self.db.query(PullRequest).filter(
            PullRequest.repository_id == repository.id,
            PullRequest.number == pr_number
        ).first()

        if pull_request:
            # Update
            pull_request.title = title
            pull_request.description = description
            pull_request.state = state
            pull_request.head_sha = head_sha
            pull_request.base_sha = base_sha
            pull_request.changed_files = changed_files_count
            self.db.commit()
            self.db.refresh(pull_request)
        else:
            # Create
            pull_request = PullRequest(
                repository_id=repository.id,
                number=pr_number,
                title=title,
                description=description,
                author_username=author,
                source_branch=source_branch,
                target_branch=target_branch,
                state=state,
                changed_files=changed_files_count,
                head_sha=head_sha,
                base_sha=base_sha,
                provider_created_at=getattr(pr_obj, "created_at", None),
                provider_updated_at=getattr(pr_obj, "updated_at", None),
            )
            self.db.add(pull_request)
            self.db.commit()
            self.db.refresh(pull_request)

        return repository, pull_request

    async def sync_repositories(self, connection_id: int) -> Dict[str, int]:
        """
        Authoritative sync of repositories based on GitHub App installation payload.
        """
        connection = self.db.query(GitHubConnection).filter_by(id=connection_id).first()
        if not connection or not connection.installation_id:
            raise ValueError(f"GitHubConnection {connection_id} not found or missing installation_id")
            
        app_service = GitHubAppService()
        
        try:
            token = await app_service.get_installation_access_token(connection.installation_id)
            github_repos = await app_service.get_installation_repositories(token)
            
            summary = {
                "discovered": len(github_repos),
                "created": 0,
                "updated": 0,
                "unchanged": 0,
                "removed_access": 0,
                "failed": 0
            }
            
            # Map of provider_repository_id -> github repo data
            github_repo_map = {str(repo["id"]): repo for repo in github_repos}
            
            # Fetch existing repos for this connection
            existing_repos = self.db.query(Repository).filter(
                Repository.github_connection_id == connection.id
            ).all()
            
            existing_repo_map = {repo.provider_repository_id: repo for repo in existing_repos if repo.provider_repository_id}
            
            now = datetime.now(timezone.utc)
            
            # Process GitHub repos (Create / Update)
            for provider_repo_id, gh_repo in github_repo_map.items():
                owner_login = gh_repo.get("owner", {}).get("login", "")
                
                if provider_repo_id in existing_repo_map:
                    # Update
                    repo = existing_repo_map[provider_repo_id]
                    changed = False
                    if repo.full_name != gh_repo["full_name"]:
                        repo.full_name = gh_repo["full_name"]
                        changed = True
                    if repo.name != gh_repo["name"]:
                        repo.name = gh_repo["name"]
                        changed = True
                    if repo.url != gh_repo["html_url"]:
                        repo.url = gh_repo["html_url"]
                        changed = True
                    if repo.default_branch != gh_repo.get("default_branch", "main"):
                        repo.default_branch = gh_repo.get("default_branch", "main")
                        changed = True
                    if repo.access_status != "ACTIVE":
                        repo.access_status = "ACTIVE"
                        changed = True
                        
                    repo.last_synced_at = now
                    
                    if changed:
                        summary["updated"] += 1
                    else:
                        summary["unchanged"] += 1
                else:
                    # Create
                    repo = Repository(
                        provider="GITHUB",
                        provider_repository_id=provider_repo_id,
                        owner=owner_login,
                        name=gh_repo["name"],
                        full_name=gh_repo["full_name"],
                        url=gh_repo["html_url"],
                        default_branch=gh_repo.get("default_branch", "main"),
                        active=True,
                        access_status="ACTIVE",
                        data_source="LIVE",
                        github_connection_id=connection.id,
                        workspace_id=connection.workspace_id,
                        last_synced_at=now
                    )
                    self.db.add(repo)
                    summary["created"] += 1
                    
            # Process existing repos not in GitHub payload (Remove Access)
            for provider_repo_id, repo in existing_repo_map.items():
                if provider_repo_id not in github_repo_map:
                    if repo.access_status != "ACCESS_REMOVED":
                        repo.access_status = "ACCESS_REMOVED"
                        repo.last_synced_at = now
                        summary["removed_access"] += 1
                        
            # Update connection status
            connection.last_sync_status = "SUCCESS"
            connection.last_sync_error = None
            connection.last_synced_at = now
            
            self.db.commit()
            return summary
            
        except Exception as e:
            self.db.rollback()
            logger.exception("Failed to sync repositories")
            
            # Record failure state
            try:
                connection.last_sync_status = "FAILED"
                connection.last_sync_error = str(e)[:1000]
                connection.last_synced_at = datetime.now(timezone.utc)
                self.db.commit()
            except Exception as inner_e:
                logger.error(f"Failed to record sync failure: {inner_e}")
                
            raise e