import os
import subprocess
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import Project, DeployLog, slugify
from routers.webhooks import run_deploy

router = APIRouter(prefix="/api/projects", tags=["projects"])


def get_webhook_url(request: Request, slug: str, token: str) -> str:
    base = str(request.base_url)
    return f"{base}webhook/{slug}/{token}"


def validate_git_path(path: str) -> str:
    if not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path {path} does not exist on this server",
        )
    if not os.path.isdir(os.path.join(path, ".git")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path {path} is not a git repository",
        )
    result = subprocess.run(
        ["git", "-C", path, "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


class ProjectCreate(BaseModel):
    name: str
    path: str
    branch: str = "main"
    restart_command: Optional[str] = None
    github_webhook_secret: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    branch: Optional[str] = None
    restart_command: Optional[str] = None
    github_webhook_secret: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    slug: str
    path: str
    branch: str
    restart_command: Optional[str]
    has_webhook_secret: bool
    created_at: str
    webhook_url: str
    git_remote: Optional[str] = None
    last_log: Optional[dict] = None


def serialize_project(project: Project, request: Request, session: Session) -> dict:
    last_log = session.exec(
        select(DeployLog)
        .where(DeployLog.project_id == project.id)
        .order_by(DeployLog.triggered_at.desc())
    ).first()

    last_log_data = None
    if last_log:
        last_log_data = {
            "triggered_at": last_log.triggered_at.isoformat(),
            "commit_message": last_log.commit_message,
            "git_pull_status": last_log.git_pull_status,
            "restart_status": last_log.restart_status,
            "overall_status": last_log.overall_status,
        }

    return {
        "id": project.id,
        "name": project.name,
        "slug": project.slug,
        "path": project.path,
        "branch": project.branch,
        "restart_command": project.restart_command,
        "has_webhook_secret": bool(project.github_webhook_secret),
        "created_at": project.created_at.isoformat(),
        "webhook_url": get_webhook_url(request, project.slug, project.webhook_token),
        "last_log": last_log_data,
    }


class PathValidationRequest(BaseModel):
    path: str


@router.post("/validate-path")
def validate_path_endpoint(
    payload: PathValidationRequest,
    user: str = Depends(get_current_user),
):
    git_remote = validate_git_path(payload.path)
    return {"git_remote": git_remote}


@router.get("")
def list_projects(
    request: Request,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
):
    projects = session.exec(select(Project)).all()
    return [serialize_project(p, request, session) for p in projects]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    request: Request,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
):
    git_remote = validate_git_path(payload.path)

    slug = slugify(payload.name)
    existing = session.exec(select(Project).where(Project.slug == slug)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A project with a similar name already exists",
        )

    project = Project(
        name=payload.name,
        slug=slug,
        path=payload.path,
        branch=payload.branch or "main",
        restart_command=payload.restart_command,
        github_webhook_secret=payload.github_webhook_secret,
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    data = serialize_project(project, request, session)
    data["git_remote"] = git_remote
    return data


@router.get("/{project_id}")
def get_project(
    project_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    data = serialize_project(project, request, session)
    git_remote = subprocess.run(
        ["git", "-C", project.path, "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    data["git_remote"] = git_remote.stdout.strip() if git_remote.returncode == 0 else None
    return data


@router.put("/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    request: Request,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    git_remote = None
    if payload.path is not None and payload.path != project.path:
        git_remote = validate_git_path(payload.path)
        project.path = payload.path

    if payload.name is not None and payload.name != project.name:
        new_slug = slugify(payload.name)
        existing = session.exec(
            select(Project).where(Project.slug == new_slug, Project.id != project_id)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A project with a similar name already exists",
            )
        project.name = payload.name
        project.slug = new_slug

    if payload.branch is not None:
        project.branch = payload.branch
    if payload.restart_command is not None:
        project.restart_command = payload.restart_command
    if payload.github_webhook_secret is not None:
        project.github_webhook_secret = payload.github_webhook_secret

    session.add(project)
    session.commit()
    session.refresh(project)

    data = serialize_project(project, request, session)
    if git_remote is not None:
        data["git_remote"] = git_remote
    return data


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    logs = session.exec(select(DeployLog).where(DeployLog.project_id == project_id)).all()
    for log in logs:
        session.delete(log)

    session.delete(project)
    session.commit()
    return {"detail": "Project deleted"}


@router.post("/{project_id}/deploy")
def manual_deploy(
    project_id: int,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    log = run_deploy(project, session, trigger_type="manual")

    return {
        "status": log.overall_status,
        "git_pull_status": log.git_pull_status,
        "restart_status": log.restart_status,
        "git_pull_output": log.git_pull_output,
        "restart_output": log.restart_output,
    }
