import hmac
import hashlib
import json
from fastapi import APIRouter, Depends, Request, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import Repository, Deployment
from database import get_db

router = APIRouter()

@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
    x_github_delivery: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"message": "Invalid JSON"})

    # Step 5: Locate repository
    repo_url = payload.get("repository", {}).get("html_url")
    if not repo_url:
        return JSONResponse(status_code=200, content={"message": "No repository URL"})
        
    result = await db.execute(select(Repository).filter(Repository.github_url == repo_url))
    repo = result.scalars().first()
    
    if not repo:
        return JSONResponse(status_code=200, content={"message": "Repository not registered"})

    # Step 1: Validate HMAC
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing signature")
    
    secret = repo.webhook_secret.encode('utf-8')
    expected_signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Step 2: Event type
    if x_github_event != "push":
        return JSONResponse(status_code=200, content={"message": "Ignored non-push event"})
        
    # Step 3: Branch ref
    ref = payload.get("ref")
    if ref != "refs/heads/main":
        return JSONResponse(status_code=200, content={"message": "Ignored non-main push"})
        
    # Step 4: Deduplication
    if not x_github_delivery:
        return JSONResponse(status_code=200, content={"message": "Missing delivery ID"})
        
    existing_deployment = await db.execute(select(Deployment).filter(Deployment.triggered_by == x_github_delivery))
    if existing_deployment.scalars().first():
        return JSONResponse(status_code=200, content={"message": "Duplicate delivery ID"})
        
    # Step 6: Create deployment
    commit_sha = payload.get("after")
    if not commit_sha:
        return JSONResponse(status_code=200, content={"message": "No commit SHA"})
        
    new_deployment = Deployment(
        repo_id=repo.id,
        commit_sha=commit_sha,
        triggered_by=x_github_delivery,
        status="PENDING"
    )
    
    db.add(new_deployment)
    await db.commit()
    
    return JSONResponse(status_code=200, content={"message": "Deployment created"})
