import getpass
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Tuple

from models import Project

SERVICE_PREFIX = "gitpulse-app-"


def systemd_available() -> bool:
    return platform.system() == "Linux" and shutil.which("systemctl") is not None


def project_service_name(slug: str) -> str:
    return f"{SERVICE_PREFIX}{slug}"


def _service_file_path(slug: str) -> Path:
    return Path(f"/etc/systemd/system/{project_service_name(slug)}.service")


def ensure_project_service(project: Project) -> Tuple[str, str]:
    """Create/update and (re)start a systemd service for a project's launch
    command. Returns (output, status) where status is "success" or "failed".
    """
    if not systemd_available():
        return "Auto-managed services require Linux with systemd.", "failed"

    if not project.launch_command:
        return "No launch command configured.", "failed"

    service_name = project_service_name(project.slug)
    service_file = _service_file_path(project.slug)
    run_user = getpass.getuser()

    service_contents = (
        "[Unit]\n"
        f"Description=GitPulse managed process for {project.name}\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"User={run_user}\n"
        f"WorkingDirectory={project.path}\n"
        f"ExecStart={project.launch_command}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )

    needs_write = not service_file.exists() or service_file.read_text() != service_contents
    output_lines = []

    try:
        if needs_write:
            output_lines.append(f"Installing systemd service '{service_name}'...")
            subprocess.run(
                ["sudo", "tee", str(service_file)],
                input=service_contents, text=True, capture_output=True, check=True,
            )
            subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                capture_output=True, text=True, check=True,
            )
            subprocess.run(
                ["sudo", "systemctl", "enable", service_name],
                capture_output=True, text=True, check=True,
            )

        restart_result = subprocess.run(
            ["sudo", "systemctl", "restart", service_name],
            capture_output=True, text=True,
        )
        output_lines.append(restart_result.stdout)
        output_lines.append(restart_result.stderr)

        status_result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True, text=True,
        )
        is_active = status_result.stdout.strip() == "active"
        output_lines.append(f"systemctl is-active {service_name}: {status_result.stdout.strip()}")

        status = "success" if restart_result.returncode == 0 and is_active else "failed"
        return "\n".join(line for line in output_lines if line), status

    except subprocess.CalledProcessError as exc:
        output_lines.append(f"Failed to manage systemd service: {exc}")
        if exc.stderr:
            output_lines.append(exc.stderr)
        return "\n".join(line for line in output_lines if line), "failed"


def remove_project_service(slug: str) -> None:
    if not systemd_available():
        return

    service_name = project_service_name(slug)
    service_file = _service_file_path(slug)
    if not service_file.exists():
        return

    try:
        subprocess.run(["sudo", "systemctl", "stop", service_name], capture_output=True, text=True)
        subprocess.run(["sudo", "systemctl", "disable", service_name], capture_output=True, text=True)
        subprocess.run(["sudo", "rm", str(service_file)], capture_output=True, text=True)
        subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True, text=True)
    except Exception:
        pass
