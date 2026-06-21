# GitPulse

GitPulse is a self-hosted GitHub webhook deployment manager. Point a GitHub
repository's webhook at it, and on every push it will `git fetch` + hard
reset your server-side checkout to match, then run a restart command (e.g.
`pm2 restart app`). It also supports triggering a deploy manually from the
dashboard.

Everything runs from a single FastAPI app with a SQLite database — no
external services, message queues, or build step for the frontend (plain
HTML/CSS/JS + Alpine.js via CDN).

## How it works

1. You register a **project** in the dashboard: a name, the absolute path to
   a git checkout already on this server, the branch to track, and
   (optionally) a restart command and a GitHub webhook secret.
2. GitPulse generates a unique webhook URL for that project:
   `https://your-domain:8443/webhook/{slug}/{token}`.
3. You paste that URL into the GitHub repo's **Settings → Webhooks** page.
4. On every push GitHub sends to that URL, GitPulse:
   - verifies the payload signature (if you set a secret) using HMAC-SHA256
   - ignores the push if it's not for the configured branch
   - runs `git fetch --all && git reset --hard origin/{branch}` in the
     project's path
   - runs the restart command, if one is configured
   - records everything (commit, pusher, command output, pass/fail) as a
     deploy log
5. The dashboard shows every project's last deploy status and a full
   timeline of deploy logs, expandable to see raw command output.

Authentication is a single admin account (no multi-user support) — you log
in with a username/password from `.env`, and the dashboard talks to the API
using a JWT stored in `localStorage`.

## Requirements

- Python 3.10+
- Git installed and on `PATH` (used to validate project paths and to run
  `git fetch` / `git reset`)
- The project(s) you want to deploy must already be cloned somewhere on this
  same server — GitPulse does not clone repos for you, it only pulls
  updates to an existing checkout

## Setup

The fastest path is the bundled setup script — it creates the virtual
environment, installs dependencies, and launches the app, all in one step.
Re-running it later just reuses the existing venv and starts the app again.

**Linux/macOS:**

```bash
./setup.sh
```

**Windows (PowerShell):**

```powershell
.\setup.ps1
```

If you'd rather do it manually:

```bash
# from the project root
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
python start.py
```

The first time it runs, `start.py` will:

1. Create `.env` from scratch if missing, and generate a random
   `SECRET_KEY` (used to sign dashboard login JWTs — unrelated to GitHub
   webhook secrets, which are configured per-project).
2. Prompt you in the terminal to set an admin password, and save it to
   `.env` as `ADMIN_PASSWORD`. Note: this is stored in **plaintext** — by
   design, to keep the single-admin self-hosted setup simple. Keep
   `.env` out of version control and restrict its file permissions.
3. Look up your server's public IP (via `https://api.ipify.org`), build a
   `{ip}.nip.io` domain, and generate a self-signed SSL certificate for it
   under `certs/` (skipped on subsequent runs if the cert already exists).
4. **On Linux**, install and start GitPulse as a `systemd` service named
   `gitpulse` (using `sudo`, so it may prompt for your password) so it
   survives reboots and restarts automatically if it crashes. The script
   then exits and `systemd` takes over running the app.
5. **On Windows/macOS** (no `systemd`), it just starts the app directly in
   the foreground on `https://0.0.0.0:8443`.

On every later run, `start.py` reuses the existing `.env` and certificate,
and on Linux just restarts the already-installed service.

Once installed as a service, manage it directly with:

```bash
sudo systemctl status gitpulse
sudo systemctl restart gitpulse
sudo systemctl stop gitpulse
sudo journalctl -u gitpulse -f   # tail logs
```

### Running locally vs. exposing it publicly

- **Local/dev use:** open `https://localhost:8443` (or `127.0.0.1`). You'll
  get a certificate warning since the cert's hostname is your public IP's
  `nip.io` domain, not `localhost` — click through it.
- **Receiving real GitHub webhooks:** GitHub needs to reach this server over
  the public internet, so you'll need port-forwarding on your router (
  external `8443` → this machine's LAN IP, port `8443`) and a firewall rule
  allowing inbound traffic on that port. Then use
  `https://{your-public-ip}.nip.io:8443` as the base for webhook URLs (this
  is generated automatically from the incoming request, so no extra config
  is needed once the network path is open).
- Since the certificate is self-signed, GitHub will refuse to verify it by
  default — when adding the webhook in GitHub, check **"Disable SSL
  verification"** (shown as a hint in the dashboard's webhook URL field
  too).

## Using the dashboard

1. **Login** — go to `/login`, sign in with `ADMIN_USERNAME` /
   `ADMIN_PASSWORD` from `.env` (default username is `admin`).
2. **Add a project** — click **+ Add Project** and fill in:
   - **Project Name** — used to generate the project's slug/webhook URL
   - **Server Path** — absolute path to an existing git checkout on this
     server (e.g. `/var/www/my-app`). On blur, GitPulse checks the path
     exists and contains a `.git` folder, and shows the detected `origin`
     remote so you can confirm it's the right repo.
   - **Branch** — which branch triggers a deploy (default `main`)
   - **Restart Command** *(optional)* — shell command run after a
     successful pull, e.g. `pm2 restart app`, `systemctl restart app`, or
     `docker compose up -d`. Leave blank to skip restarting anything.
   - **GitHub Webhook Secret** *(optional but recommended)* — if set,
     incoming webhook payloads are verified against it; mismatched/missing
     signatures are rejected with 401.
3. After saving, you'll get a **webhook URL** — copy it into the GitHub
   repo's webhook settings (`Settings → Webhooks → Add webhook`), set
   content type to `application/json`, and (if you set a secret above) put
   the same secret in GitHub's "Secret" field.
4. **Deploy** — pushing to the configured branch on GitHub triggers a
   deploy automatically. You can also click the ▶ **Deploy Now** button on
   a project card to trigger one manually at any time.
5. **Settings** — the gear icon on a project card opens a drawer to edit any
   field, rotate the webhook secret, or delete the project (which also
   deletes its deploy history).
6. **Logs** — the Logs page lists every deploy (manual or webhook-triggered)
   across all projects, newest first, filterable by project and by
   success/failure. Expand a log entry to see the full git pull output and
   restart command output.

## Project structure

```
gitpulse/
├── main.py            # FastAPI app setup, route mounting, page routes
├── start.py            # First-run setup: .env, admin password, SSL cert, launches uvicorn
├── database.py         # SQLite engine/session via SQLModel
├── models.py            # Project and DeployLog tables
├── auth.py               # JWT issuing/verification, password check
├── routers/
│   ├── auth.py          # POST /api/auth/login
│   ├── projects.py    # CRUD + path validation + manual deploy trigger
│   ├── webhooks.py    # GitHub webhook receiver + shared deploy logic
│   └── logs.py          # Deploy log listing/filtering
├── static/
│   ├── css/style.css   # Dark theme, all styling
│   └── js/
│       ├── app.js        # Auth/toast/fetch helpers, sidebar nav
│       ├── projects.js  # Projects view + Add/Settings drawers
│       └── logs.js       # Logs view + filters
├── templates/
│   ├── login.html
│   └── index.html        # Single-page dashboard shell (Alpine.js)
└── certs/                  # Self-signed cert + key (generated by start.py)
```

## Notes & limitations

- Single admin user only — there's no user management or multi-tenant
  support.
- The admin password lives in `.env` as plaintext; treat that file as a
  secret (it's already excluded via `.gitignore`).
- Restart commands run via the shell (`subprocess.run(..., shell=True)`), so
  they behave like whatever shell is available on the host OS — on Windows
  that's `cmd.exe`, so Linux-flavored examples like `systemctl restart app`
  won't work there as-is.
- GitPulse assumes the project path is already a git clone with a remote
  configured — it never runs `git clone` for you.
