import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from schemas import CreateRepositoryRequest, RepositoryResponse
from models import Repository
from database import get_db

router = APIRouter()

@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(repo_in: CreateRepositoryRequest, db: AsyncSession = Depends(get_db)):
    # Check for duplicate
    result = await db.execute(select(Repository).filter(Repository.github_url == repo_in.github_url))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Repository with this GitHub URL already exists.")
    
    # Generate webhook secret
    webhook_secret = secrets.token_hex(32)
    
    new_repo = Repository(
        name=repo_in.name,
        github_url=repo_in.github_url,
        webhook_secret=webhook_secret
    )
    
    db.add(new_repo)
    try:
        await db.commit()
        await db.refresh(new_repo)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Database error occurred.")
        
    return new_repo

@router.get("", response_model=list[RepositoryResponse])
async def get_repositories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Repository))
    return result.scalars().all()

@router.get("/{repo_id}", response_model=RepositoryResponse)
async def get_repository(repo_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Repository).filter(Repository.id == repo_id))
    repo = result.scalars().first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found.")
    return repo

@router.get("/{repo_id}/deployments")
async def get_repository_deployments(repo_id: int, db: AsyncSession = Depends(get_db)):
    from schemas import DeploymentResponse
    from models import Deployment
    result = await db.execute(select(Deployment).filter(Deployment.repo_id == repo_id).order_by(Deployment.id.desc()))
    deployments = result.scalars().all()
    return deployments
