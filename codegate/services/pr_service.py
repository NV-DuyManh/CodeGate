from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from codegate.api.exceptions import ConflictException, NotFoundException
from codegate.database.models import Provider, PullRequest, Repository, State
from codegate.repositories.pr_store import pr_store
from codegate.repositories.repo_store import repo_store
from codegate.schemas.pull_request import PullRequestCreate, PullRequestUpdate


class PullRequestService:
    def create(self, db: Session, repository_id: int, pr_in: PullRequestCreate, workspace_id: int) -> PullRequest:
        from codegate.services.repository_service import repository_service
        repository_service.get(db, repository_id, workspace_id)
        
        # Check duplicate PR in repo
        existing = pr_store.get_by_repo_and_number(db, repository_id, pr_in.number)
        if existing:
            raise ConflictException(f"Pull request #{pr_in.number} already exists in this repository")
            
        try:
            dump = pr_in.model_dump()
            dump["repository_id"] = repository_id
            return pr_store.create(db, obj_in=dump)
        except IntegrityError:
            db.rollback()
            raise ConflictException("Database integrity error on pull request creation")

    def get(self, db: Session, pr_id: int, workspace_id: int) -> PullRequest:
        pr = pr_store.get_by_id(db, pr_id)
        if not pr:
            raise NotFoundException("Pull request not found")
        
        from codegate.services.repository_service import repository_service
        repository_service.get(db, pr.repository_id, workspace_id)
        
        return pr

    def list(self, db: Session, repository_id: Optional[int] = None, state: Optional[State] = None, author: Optional[str] = None, search: Optional[str] = None, skip: int = 0, limit: int = 20, workspace_id: Optional[int] = None) -> Tuple[List[PullRequest], int]:
        stmt = select(PullRequest)
        if workspace_id:
            stmt = stmt.join(Repository).where(Repository.workspace_id == workspace_id)
        if repository_id:
            stmt = stmt.where(PullRequest.repository_id == repository_id)
        if state:
            stmt = stmt.where(PullRequest.state == state)
        if author:
            stmt = stmt.where(PullRequest.author_username == author)
        if search:
            stmt = stmt.where(PullRequest.title.ilike(f"%{search}%"))
            
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = db.scalar(count_stmt)
        
        stmt = stmt.offset(skip).limit(limit)
        items = list(db.scalars(stmt).all())
        
        return items, total

    def update(self, db: Session, pr_id: int, pr_in: PullRequestUpdate, workspace_id: int) -> PullRequest:
        pr = self.get(db, pr_id, workspace_id)
        try:
            return pr_store.update(db, db_obj=pr, obj_in=pr_in.model_dump(exclude_unset=True))
        except IntegrityError:
            db.rollback()
            raise ConflictException("Database integrity error on pull request update")

pr_service = PullRequestService()
