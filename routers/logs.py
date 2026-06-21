from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import DeployLog, Project

router = APIRouter(prefix="/api/logs", tags=["logs"])


def serialize_log(log: DeployLog, project_name: Optional[str], restart_command: Optional[str] = None) -> dict:
    return {
        "id": log.id,
        "project_id": log.project_id,
        "project_name": project_name,
        "triggered_at": log.triggered_at.isoformat(),
        "trigger_type": log.trigger_type,
        "pusher_username": log.pusher_username,
        "commit_sha": log.commit_sha,
        "commit_message": log.commit_message,
        "branch": log.branch,
        "git_pull_output": log.git_pull_output,
        "git_pull_status": log.git_pull_status,
        "restart_output": log.restart_output,
        "restart_status": log.restart_status,
        "restart_command": restart_command,
        "overall_status": log.overall_status,
    }


@router.get("")
def list_logs(
    project_id: Optional[int] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
):
    query = select(DeployLog)
    if project_id is not None:
        query = query.where(DeployLog.project_id == project_id)
    if status_filter is not None:
        query = query.where(DeployLog.overall_status == status_filter)
    query = query.order_by(DeployLog.triggered_at.desc())

    logs = session.exec(query).all()
    all_projects = session.exec(select(Project)).all()
    names = {p.id: p.name for p in all_projects}
    restart_commands = {p.id: p.restart_command for p in all_projects}

    return [
        serialize_log(log, names.get(log.project_id), restart_commands.get(log.project_id))
        for log in logs
    ]


@router.get("/{project_id}")
def get_project_logs(
    project_id: int,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    logs = session.exec(
        select(DeployLog)
        .where(DeployLog.project_id == project_id)
        .order_by(DeployLog.triggered_at.desc())
    ).all()

    return [serialize_log(log, project.name, project.restart_command) for log in logs]
