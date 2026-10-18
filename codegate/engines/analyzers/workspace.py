import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from codegate.config.settings import settings

logger = logging.getLogger(__name__)

class AnalyzerWorkspace:
    """
    Manages an isolated workspace for static analysis tools to run against.
    Clones the repository and checks out the specific SHA for the pull request.
    """
    def __init__(self, clone_url: str, head_sha: str, token: Optional[str] = None):
        self.clone_url = clone_url
        self.head_sha = head_sha
        self.token = token
        self.workspace_dir: Optional[str] = None

    def _get_auth_url(self) -> str:
        """Inject token into URL if available."""
        if not self.token:
            return self.clone_url
        
        # Simple injection for github/gitlab clone urls
        # https://github.com/org/repo.git -> https://x-access-token:<token>@github.com/org/repo.git
        if self.clone_url.startswith("https://"):
            parts = self.clone_url.split("https://", 1)
            return f"https://x-access-token:{self.token}@{parts[1]}"
        return self.clone_url

    def prepare(self) -> str:
        """Creates the workspace and checks out the code."""
        self.workspace_dir = tempfile.mkdtemp(prefix="codegate_analysis_")
        logger.info(f"Created temporary workspace at {self.workspace_dir}")

        auth_url = self._get_auth_url()
        
        try:
            # We clone the repo. Doing a full clone can be slow, so we try fetching the specific SHA
            # Initialize empty git repo
            subprocess.run(["git", "init"], cwd=self.workspace_dir, check=True, capture_output=True,
                           timeout=settings.ANALYZER_TIMEOUT_SECONDS)
            
            # Add remote
            subprocess.run(["git", "remote", "add", "origin", auth_url], cwd=self.workspace_dir,
                           check=True, capture_output=True, timeout=settings.ANALYZER_TIMEOUT_SECONDS)
            
            # Fetch the specific SHA. Note: Many git servers allow fetching by SHA (allowReachableSHA1InWant)
            # If this fails due to server restrictions, a shallow clone of the branch might be needed,
            # but for this system, we try fetching the exact SHA first.
            fetch_cmd = ["git", "fetch", "--depth", "1", "origin", self.head_sha]
            subprocess.run(fetch_cmd, cwd=self.workspace_dir, check=True, capture_output=True,
                           timeout=settings.ANALYZER_TIMEOUT_SECONDS)
            
            # Checkout
            subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=self.workspace_dir, check=True,
                           capture_output=True, timeout=settings.ANALYZER_TIMEOUT_SECONDS)
            
            return self.workspace_dir
        except subprocess.CalledProcessError as e:
            stderr = e.stderr or b""
            message = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else str(stderr)
            if self.token:
                message = message.replace(self.token, "[REDACTED]")
            logger.error("Failed to prepare workspace: %s", message)
            self.cleanup()
            # CalledProcessError includes argv, which may contain the authenticated remote URL.
            raise RuntimeError("Workspace preparation failed: git error") from None
        except subprocess.TimeoutExpired:
            logger.error("Git workspace preparation timed out")
            self.cleanup()
            raise RuntimeError("Workspace preparation failed: git timed out") from None
        except OSError:
            logger.error("Git could not be launched during workspace preparation")
            self.cleanup()
            raise RuntimeError("Workspace preparation failed: git unavailable") from None

    def cleanup(self):
        """Cleans up the temporary workspace."""
        if self.workspace_dir and os.path.exists(self.workspace_dir):
            try:
                # Handle Windows read-only file issues with git objects
                def remove_readonly(func, path, _):
                    import stat
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                
                shutil.rmtree(self.workspace_dir, onerror=remove_readonly)
                logger.info(f"Cleaned up workspace at {self.workspace_dir}")
            except Exception as e:
                logger.error(f"Failed to cleanup workspace {self.workspace_dir}: {e}")
            finally:
                self.workspace_dir = None
