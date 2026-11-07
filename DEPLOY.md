# Deploying DecOps

## A. VPS with Docker (HTTPS included)

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
