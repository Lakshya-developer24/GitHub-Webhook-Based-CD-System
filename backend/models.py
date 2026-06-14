from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    github_url = Column(String, nullable=False)
    webhook_secret = Column(String, nullable=False)
    registered_at = Column(DateTime, default=datetime.utcnow)

    deployments = relationship("Deployment", back_populates="repository")


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    commit_sha = Column(String, nullable=False)
    triggered_by = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False)
    image_name = Column(String, nullable=True)
    container_name = Column(String, nullable=True)
    deployment_url = Column(String, nullable=True)
    logs = Column(String, nullable=True)
    error = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    repository = relationship("Repository", back_populates="deployments")
