from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional

class CreateRepositoryRequest(BaseModel):
    name: str = Field(..., description="The name of the repository")
    github_url: str = Field(..., description="The full GitHub URL of the repository")

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        if not v.startswith("https://github.com/"):
            raise ValueError("github_url must start with https://github.com/")
        return v

class RepositoryResponse(BaseModel):
    id: int
    name: str
    github_url: str
    webhook_url: Optional[str] = "/api/webhooks/github"
    webhook_secret: str
    registered_at: datetime

    class Config:
        from_attributes = True
