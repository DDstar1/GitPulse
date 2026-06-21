import hashlib
import hmac
import subprocess
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import Session, select

from database import engine
from models import DeployLog, Project
from process_manager import ensure_project_service

router = APIRouter(tags=["webhooks"])


def run_deploy(project: Project, session: Session, trigger_type: str,
               pusher_username: Optional[str] = None,
               commit_sha: Optional[str] = None,
               commit_message: Optional[str] = None,
               branch: Optional[str] = None) -> DeployLog:
    pull_cmd = (
        f"cd \"{project.path}\" && git fetch --all && "
        f"git reset --hard origin/{project.branch}"
    )
    pull_result = subprocess.run(
        pull_cmd, shell=True, capture_output=True, text=True
    )
    git_pull_output = (pull_result.stdout or "") + (pull_result.stderr or "")
    git_pull_status = "success" if pull_result.returncode == 0 else "failed"

    restart_output: Optional[str] = None
    restart_status = "skipped"

    if project.launch_command:
        restart_output, restart_status = ensure_project_service(project)
    elif project.restart_command:
        restart_result = subprocess.run(
            project.restart_command, shell=True, capture_output=True,
            text=True, cwd=project.path
        )
        restart_output = (restart_result.stdout or "") + (restart_result.stderr or "")
        restart_status = "success" if restart_result.returncode == 0 else "failed"

    if git_pull_status == "success" and restart_status in ("success", "skipped"):
        overall_status = "success"
    else:
        overall_status = "failed"

    log = DeployLog(
        project_id=project.id,
        triggered_at=datetime.utcnow(),
        trigger_type=trigger_type,
        pusher_username=pusher_username,
        commit_sha=commit_sha,
        commit_message=commit_message,
        branch=branch,
        git_pull_output=git_pull_output,
        git_pull_status=git_pull_status,
        restart_output=restart_output,
        restart_status=restart_status,
        overall_status=overall_status,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@router.post("/webhook/{slug}/{token}")
async def receive_webhook(slug: str, token: str, request: Request):
    with Session(engine) as session:
        project = session.exec(
            select(Project).where(Project.slug == slug, Project.webhook_token == token)
        ).first()

        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        body = await request.body()

        signature_header = request.headers.get("X-Hub-Signature-256", "")
        signature_error = None
        if not project.github_webhook_secret:
            signature_error = "No webhook secret configured for this project"
        elif not signature_header.startswith("sha256="):
            signature_error = "Missing signature"
        else:
            expected_signature = hmac.new(
                project.github_webhook_secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
            provided_signature = signature_header[len("sha256="):]
            if not hmac.compare_digest(expected_signature, provided_signature):
                signature_error = "Invalid signature — webhook secret does not match"

        if signature_error:
            log = DeployLog(
                project_id=project.id,
                triggered_at=datetime.utcnow(),
                trigger_type="webhook",
                git_pull_output=signature_error,
                git_pull_status="failed",
                restart_status="skipped",
                overall_status="failed",
            )
            session.add(log)
            session.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=signature_error)

        try:
            payload = await request.json()
        except Exception:
            payload = {}

        event_type = request.headers.get("X-GitHub-Event", "")

        if event_type == "ping":
            log = DeployLog(
                project_id=project.id,
                triggered_at=datetime.utcnow(),
                trigger_type="webhook",
                git_pull_output="GitHub ping event received (connectivity test, no deploy triggered).",
                git_pull_status="skipped",
                restart_status="skipped",
                overall_status="ignored",
            )
            session.add(log)
            session.commit()
            return {"status": "ignored", "reason": "ping event"}

        pusher_username = (payload.get("pusher") or {}).get("name")
        head_commit = payload.get("head_commit") or {}
        commit_message = head_commit.get("message")
        commit_sha = head_commit.get("id")
        ref = payload.get("ref", "")
        pushed_branch = ref.replace("refs/heads/", "") if ref else None

        if pushed_branch != project.branch:
            log = DeployLog(
                project_id=project.id,
                triggered_at=datetime.utcnow(),
                trigger_type="webhook",
                pusher_username=pusher_username,
                branch=pushed_branch,
                git_pull_output=f"Push to '{pushed_branch}' ignored (this project tracks '{project.branch}').",
                git_pull_status="skipped",
                restart_status="skipped",
                overall_status="ignored",
            )
            session.add(log)
            session.commit()
            return {"status": "ignored", "reason": "branch mismatch"}

        log = run_deploy(
            project, session, trigger_type="webhook",
            pusher_username=pusher_username,
            commit_sha=commit_sha,
            commit_message=commit_message,
            branch=pushed_branch,
        )

        return {
            "status": log.overall_status,
            "git_pull_status": log.git_pull_status,
            "restart_status": log.restart_status,
        }
