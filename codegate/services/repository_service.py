from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from codegate.api.exceptions import ConflictException, NotFoundException
from codegate.database.models import Provider, Repository
from codegate.repositories.repo_store import repo_store
from codegate.schemas.repository import RepositoryCreate, RepositoryUpdate


class RepositoryService:
    def create(self, db: Session, repo_in: RepositoryCreate, workspace_id: int) -> Repository:
        # Check duplicate
        stmt = select(Repository).where(Repository.provider == repo_in.provider).where(Repository.full_name == repo_in.full_name).where(Repository.workspace_id == workspace_id)
        existing = db.scalar(stmt)
        if existing:
            raise ConflictException(f"Repository {repo_in.provider}:{repo_in.full_name} already exists in this workspace")
        
        try:
            obj_in = repo_in.model_dump()
            obj_in["workspace_id"] = workspace_id
            return repo_store.create(db, obj_in=obj_in)
        except IntegrityError:
            db.rollback()
            raise ConflictException("Database integrity error on repository creation")

    def get(self, db: Session, repo_id: int, workspace_id: int) -> Repository:
        repo = repo_store.get_by_id(db, repo_id)
        if not repo or repo.workspace_id != workspace_id:
            raise NotFoundException("Repository not found")
        return repo

    def list(self, db: Session, provider: Optional[Provider] = None, active: Optional[bool] = None, search: Optional[str] = None, skip: int = 0, limit: int = 20, workspace_id: Optional[int] = None) -> Tuple[List[Repository], int]:
        filters = {}
        if provider:
            filters["provider"] = provider
        if active is not None:
            filters["active"] = active
            
        # In a real app we'd add search filter to repo_store
        # For simplicity, passing directly if supported by our store, else relying on base store
        # Here we just use the list from base_store and maybe implement simple filtering
        
        # Let's use SQLAlchemy directly for more complex queries
        from sqlalchemy import func, select
        stmt = select(Repository)
        if workspace_id:
            stmt = stmt.where(Repository.workspace_id == workspace_id)
        if provider:
            stmt = stmt.where(Repository.provider == provider)
        if active is not None:
            stmt = stmt.where(Repository.active == active)
        if search:
            stmt = stmt.where(Repository.full_name.ilike(f"%{search}%"))
            
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = db.scalar(count_stmt)
        
        stmt = stmt.offset(skip).limit(limit)
        items = list(db.scalars(stmt).all())
        
        return items, total

    def update(self, db: Session, repo_id: int, repo_in: RepositoryUpdate, workspace_id: int) -> Repository:
        repo = self.get(db, repo_id, workspace_id)
        try:
            return repo_store.update(db, db_obj=repo, obj_in=repo_in.model_dump(exclude_unset=True))
        except IntegrityError:
            db.rollback()
            raise ConflictException("Database integrity error on repository update")

    def delete(self, db: Session, repo_id: int, workspace_id: int) -> Repository:
        repo = self.get(db, repo_id, workspace_id)
        # Soft delete
        return repo_store.update(db, db_obj=repo, obj_in={"active": False})

repository_service = RepositoryService()
