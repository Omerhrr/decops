# Deploying DecOps

## A0. Quick start: decops.rogan.live on a fresh VPS (Ubuntu/Debian)

1. **DNS:** at your DNS provider create an `A` record `decops` (for `decops.rogan.live`) pointing to the VPS IPv4 address (add an `AAAA` only if the VPS has working IPv6). If you use Cloudflare, set it to **DNS only** (grey cloud) until the certificate is issued.
2. **Server prep** (as root or with sudo):
   ```bash
   curl -fsSL https://get.docker.com | sh
   ufw allow OpenSSH && ufw allow 80,443/tcp && ufw --force enable
   ```
3. **Clone and configure:**
   ```bash
   git clone <your-repo-url> decops && cd decops
   bash scripts/gen_env.sh decops.rogan.live you@yourcompany.com   # writes .env with fresh secrets, prints the admin password once
   nano .env                                                    # optional: SMTP settings
   docker compose up -d --build
   docker compose ps && docker compose logs -f api
   ```
4. Open `https://decops.rogan.live`, sign in with the printed admin credentials, then change the password and turn on two-factor under *Account*.

Docker publishes ports 80 and 443 itself and bypasses `ufw` for them, which is fine here because only Caddy publishes anything.
If the certificate does not issue, check `docker compose logs caddy` (almost always DNS not yet pointing at the server, or ports 80/443 blocked by the provider's firewall).

## A1. The server already runs another project's Caddy (e.g. ~/opt/interdec)

Only one container can own ports 80/443, so DecOps reuses the existing Caddy instead of starting its own.

1. **Find the existing Caddy's network and config file:**
   ```bash
   docker inspect interdec-caddy-1 --format '{{json .NetworkSettings.Networks}}' | grep -o '"[a-z0-9_-]*":{' | head
   docker inspect interdec-caddy-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
   ```
   The network is usually `<project-folder>_default` (e.g. `interdec_default`). The mount whose destination is `/etc/caddy/Caddyfile` is the file to edit.
2. **Clone and configure DecOps** (next to the other project, e.g. `~/opt/decops`):
   ```bash
   cd ~/opt && git clone <your-repo-url> decops && cd decops
   bash scripts/gen_env.sh decops.rogan.live you@yourcompany.com
   echo 'EDGE_NETWORK=interdec_default' >> .env      # the network from step 1
   docker compose -f docker-compose.yml -f docker-compose.shared-caddy.yml up -d --build
   docker compose -f docker-compose.yml -f docker-compose.shared-caddy.yml ps
   ```
3. **Add a site block to the existing Caddyfile** (keep the existing blocks untouched):
   ```
   decops.rogan.live {
   	encode zstd gzip
   	request_body {
   		max_size 30MB
   	}
   	header Strict-Transport-Security "max-age=31536000; includeSubDomains"
   	reverse_proxy decops-web:3000
   }
   ```
4. **Reload Caddy without downtime** (validates first, so a typo cannot take the other site down):
   ```bash
   docker exec interdec-caddy-1 caddy validate --config /etc/caddy/Caddyfile
   docker exec interdec-caddy-1 caddy reload --config /etc/caddy/Caddyfile
   ```
5. Make sure the DNS `A` record `decops.rogan.live` points at this server, then open `https://decops.rogan.live`.

Use the same `-f docker-compose.yml -f docker-compose.shared-caddy.yml` flags for every later command (`logs`, `down`, `up -d --build` after `git pull`).

## A. VPS with Docker (details)

1. Point a DNS `A` record for your domain (e.g. `ops.example.com`) at the VPS. Open ports 80 and 443.
2. Install Docker + Compose plugin, clone the repo, then:
   ```bash
   cp .env.example .env      # fill every value; generate secrets with: openssl rand -hex 32
   docker compose up -d --build
   docker compose logs -f api
   ```
3. Open `https://<DOMAIN>` and sign in with `DECOPS_SEED_ADMIN_EMAIL` / `DECOPS_SEED_ADMIN_PASSWORD`, then change the password.

Only Caddy (80/443) is published; Postgres, API and web are on the internal Docker network. Caddy obtains and renews certificates automatically.

**Backups (automatic):** the `backup` service writes a database dump and an attachments archive to `./backups` every night (02:00 UTC) and keeps 14 days. Copy that folder off the server regularly (rsync, rclone to S3/Backblaze); a backup on the same disk is not a disaster-recovery plan.
**Restore:**
```bash
docker compose stop api web
docker compose exec -T db pg_restore --clean --if-exists --no-owner -U decops -d decops < backups/db_<timestamp>.dump
docker run --rm -v decops_appdata:/data -v "$PWD/backups":/b alpine sh -c "cd /data && tar -xzf /b/files_<timestamp>.tar.gz"
docker compose start api web
```
(Replace `decops_` with your compose project name, shown by `docker volume ls`.)
**Update:** `git pull && docker compose up -d --build` (migrations run automatically on API start).

## B. Render

1. Push the repo to GitHub, then Render > New > Blueprint > select it (`render.yaml`).
2. When prompted, set `DECOPS_SEED_ADMIN_EMAIL`, `DECOPS_SEED_ADMIN_PASSWORD` and `DECOPS_TRUSTED_ORIGINS` (e.g. `["https://decops-web.onrender.com"]`, or your custom domain once attached).
3. The API is a private service with a persistent disk (`/data`) and needs a paid instance type; the web service is the only public endpoint.

## Notes
- Demo staff accounts share a known password and are **not** seeded in production (`DECOPS_SEED_DEMO_DATA=false`).
- In production the API refuses to start with default secrets, insecure cookies, SQLite, or no trusted origins.
- Run a single API worker: the notification outbox worker runs inside the API process.
- `FORWARDED_ALLOW_IPS` defaults to `*` because the API is never published outside the internal network; restrict it if you expose the API port.
- Add rate limiting at the edge (Cloudflare, or a Caddy rate-limit plugin) before opening to the public internet; the app only throttles per-account logins.

## Account security features
- **Email:** set `DECOPS_EMAIL_NOTIFICATIONS_ENABLED=true` and the `DECOPS_SMTP_*` values (use `DECOPS_SMTP_SSL=true` with port 465) so reset links and notifications are emailed. Admins can verify it with "Send a test email to me" under Account → Notifications. Without it, no reset email is sent in production.
- **First login:** admin-created users must choose their own password. The seeded admin should change the password in *Account security* on first sign-in.
- **Two-factor:** users enable TOTP themselves in *Account security*. If someone loses their device, an administrator uses *Reset two-factor* (API: `POST /api/v1/users/{id}/reset-mfa`).
- **Rate limiting** is in-process (login, reset and password endpoints, per IP). Keep a single API worker.
- **Sentry:** set `DECOPS_SENTRY_DSN` to enable error tracking for the API (no personal data is sent).
