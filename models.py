import re
import secrets
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


def slugify(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or secrets.token_hex(4)


def generate_webhook_token() -> str:
    return secrets.token_hex(4)


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    slug: str = Field(unique=True, index=True)
    path: str
    branch: str = Field(default="main")
    restart_command: Optional[str] = Field(default=None)
    launch_command: Optional[str] = Field(default=None)
    webhook_token: str = Field(default_factory=generate_webhook_token)
    github_webhook_secret: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DeployLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
    trigger_type: str
    pusher_username: Optional[str] = Field(default=None)
    commit_sha: Optional[str] = Field(default=None)
    commit_message: Optional[str] = Field(default=None)
    branch: Optional[str] = Field(default=None)
    git_pull_output: str
    git_pull_status: str
    restart_output: Optional[str] = Field(default=None)
    restart_status: str
    overall_status: str
