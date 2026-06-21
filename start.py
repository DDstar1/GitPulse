import getpass
import os
import secrets
from pathlib import Path

import httpx
from dotenv import load_dotenv, set_key
from passlib.context import CryptContext
from OpenSSL import crypto

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CERTS_DIR = BASE_DIR / "certs"
CERT_PATH = CERTS_DIR / "cert.pem"
KEY_PATH = CERTS_DIR / "key.pem"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def ensure_env_file() -> None:
    if not ENV_PATH.exists():
        ENV_PATH.write_text(
            "SECRET_KEY=\nADMIN_USERNAME=admin\nADMIN_PASSWORD_HASH=\n"
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

    if not os.environ.get("ADMIN_PASSWORD_HASH"):
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

        password_hash = pwd_context.hash(password)
        set_key(str(ENV_PATH), "ADMIN_PASSWORD_HASH", password_hash)
        os.environ["ADMIN_PASSWORD_HASH"] = password_hash
        print("Admin password saved.")


def fetch_public_ip() -> str:
    response = httpx.get("https://api.ipify.org", timeout=10.0)
    response.raise_for_status()
    return response.text.strip()


def generate_self_signed_cert(domain: str) -> None:
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)

    cert = crypto.X509()
    cert.get_subject().CN = domain
    cert.set_serial_number(secrets.randbits(64))
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(key)
    cert.add_extensions([
        crypto.X509Extension(
            b"subjectAltName", False, f"DNS:{domain}".encode("utf-8")
        ),
    ])
    cert.sign(key, "sha256")

    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    CERT_PATH.write_bytes(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    KEY_PATH.write_bytes(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))


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


def main() -> None:
    ensure_env_file()
    ensure_secret_key()
    ensure_admin_password()

    domain = ensure_certs()
    print(f"🚀 GitPulse running at https://{domain}:8000")

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        ssl_certfile=str(CERT_PATH),
        ssl_keyfile=str(KEY_PATH),
    )


if __name__ == "__main__":
    main()
