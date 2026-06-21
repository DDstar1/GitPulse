import datetime
import getpass
import os
import platform
import shutil
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from dotenv import load_dotenv, set_key
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CERTS_DIR = BASE_DIR / "certs"
CERT_PATH = CERTS_DIR / "cert.pem"
KEY_PATH = CERTS_DIR / "key.pem"

SERVICE_NAME = "gitpulse"
SERVICE_FILE = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")
MANAGED_ENV_VAR = "GITPULSE_MANAGED_BY_SYSTEMD"
PORT = 8443


def find_pid_on_port(port: int) -> "tuple[str, str] | None":
    """Returns (pid, descriptive line) for whatever holds the port, if found."""
    try:
        if platform.system() == "Linux" and shutil.which("ss"):
            result = subprocess.run(
                ["sudo", "ss", "-ltnp"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f":{port} " in line or line.rstrip().endswith(f":{port}"):
                    marker = "pid="
                    if marker in line:
                        pid = line.split(marker, 1)[1].split(",", 1)[0]
                        return pid, line.strip()
        elif platform.system() == "Windows" and shutil.which("netstat"):
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f":{port} " in line:
                    pid = line.split()[-1]
                    return pid, line.strip()
    except Exception:
        pass
    return None


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return True
    return False


def kill_pid(pid: str) -> bool:
    try:
        if platform.system() == "Linux":
            subprocess.run(["sudo", "kill", "-9", pid], check=True, timeout=5)
        else:
            subprocess.run(["taskkill", "/PID", pid, "/F"], check=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ensure_port_available(port: int) -> None:
    if os.environ.get(MANAGED_ENV_VAR):
        # Running inside our own systemd unit; nothing else should be bound yet.
        return

    if not is_port_in_use(port):
        return

    print(f"⚠️  Port {port} is already in use.")

    if platform.system() == "Linux" and shutil.which("systemctl"):
        status = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True, text=True,
        ).stdout.strip()
        if status == "active":
            print(f"   The '{SERVICE_NAME}' systemd service already owns it — restarting it instead.")
            subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME])
            sys.exit(0)

    found = find_pid_on_port(port)
    if not found:
        print(f"   Could not identify the process holding port {port}. Free it manually and retry.")
        sys.exit(1)

    pid, line = found
    print(f"   Found: {line}")
    print(f"   Stopping process {pid} to free the port...")

    if not kill_pid(pid):
        print(f"   Failed to stop process {pid}. Free it manually and retry.")
        sys.exit(1)

    for _ in range(10):
        time.sleep(0.5)
        if not is_port_in_use(port):
            print(f"✅ Port {port} is now free.")
            return

    print(f"   Process {pid} was stopped but port {port} is still in use. Free it manually and retry.")
    sys.exit(1)


def ensure_env_file() -> None:
    if not ENV_PATH.exists():
        ENV_PATH.write_text(
            "SECRET_KEY=\nADMIN_USERNAME=admin\nADMIN_PASSWORD=\n"
        )


def ensure_secret_key() -> None:
    load_dotenv(ENV_PATH, override=True)
    if not os.environ.get("SECRET_KEY"):
        new_secret = secrets.token_hex(32)
        set_key(str(ENV_PATH), "SECRET_KEY", new_secret)
        os.environ["SECRET_KEY"] = new_secret


def ensure_admin_password() -> None:
    load_dotenv(ENV_PATH, override=True)
    if not os.environ.get("ADMIN_USERNAME"):
        set_key(str(ENV_PATH), "ADMIN_USERNAME", "admin")
        os.environ["ADMIN_USERNAME"] = "admin"

    if not os.environ.get("ADMIN_PASSWORD"):
        print("No admin password is configured yet.")
        while True:
            password = getpass.getpass("Set an admin password: ")
            confirm = getpass.getpass("Confirm password: ")
            if not password:
                print("Password cannot be empty.")
                continue
            if password != confirm:
                print("Passwords do not match, try again.")
                continue
            break

        set_key(str(ENV_PATH), "ADMIN_PASSWORD", password)
        os.environ["ADMIN_PASSWORD"] = password
        print("Admin password saved.")


def fetch_public_ip() -> str:
    response = httpx.get("https://api.ipify.org", timeout=10.0)
    response.raise_for_status()
    return response.text.strip()


def generate_self_signed_cert(domain: str) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, domain),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(secrets.randbits(64))
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=10 * 365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(domain)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def ensure_certs() -> str:
    if CERT_PATH.exists() and KEY_PATH.exists():
        ip = fetch_public_ip()
        return f"{ip}.nip.io"

    print("🔐 Generating SSL certificate...")
    ip = fetch_public_ip()
    domain = f"{ip}.nip.io"
    generate_self_signed_cert(domain)
    print("✅ Certificate saved to certs/")
    return domain


def run_server() -> None:
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        ssl_certfile=str(CERT_PATH),
        ssl_keyfile=str(KEY_PATH),
    )


def install_or_restart_systemd_service() -> bool:
    """Install GitPulse as a systemd service and (re)start it.

    Returns True if the service is now managing the app (so the caller
    should not also run the server directly in the foreground).
    """
    if platform.system() != "Linux":
        return False

    if not shutil.which("systemctl"):
        return False

    run_user = os.environ.get("SUDO_USER") or getpass.getuser()
    python_bin = sys.executable
    script_path = str(BASE_DIR / "start.py")

    service_contents = (
        "[Unit]\n"
        "Description=GitPulse self-hosted webhook deployment manager\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"User={run_user}\n"
        f"WorkingDirectory={BASE_DIR}\n"
        f"Environment={MANAGED_ENV_VAR}=1\n"
        f"ExecStart={python_bin} {script_path}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )

    needs_write = not SERVICE_FILE.exists() or SERVICE_FILE.read_text() != service_contents

    try:
        if needs_write:
            print(f"🛠️  Installing systemd service '{SERVICE_NAME}'...")
            subprocess.run(
                ["sudo", "tee", str(SERVICE_FILE)],
                input=service_contents,
                text=True,
                capture_output=True,
                check=True,
            )
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            subprocess.run(["sudo", "systemctl", "enable", SERVICE_NAME], check=True)

        subprocess.run(["sudo", "systemctl", "restart", SERVICE_NAME], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"⚠️  Could not install/start the systemd service ({exc}).")
        print("    Falling back to running GitPulse directly in this terminal.")
        return False

    print(f"✅ GitPulse is running as the systemd service '{SERVICE_NAME}' (enabled on boot).")
    print(f"    Logs:    sudo journalctl -u {SERVICE_NAME} -f")
    print(f"    Status:  sudo systemctl status {SERVICE_NAME}")
    print(f"    Restart: sudo systemctl restart {SERVICE_NAME}")
    return True


def main() -> None:
    ensure_env_file()
    ensure_secret_key()
    ensure_admin_password()

    ensure_port_available(PORT)

    domain = ensure_certs()
    print(f"🚀 GitPulse running at https://{domain}:{PORT}")

    if os.environ.get(MANAGED_ENV_VAR):
        # Already running inside the systemd service we installed; just serve.
        run_server()
        return

    if install_or_restart_systemd_service():
        return

    run_server()


if __name__ == "__main__":
    main()
