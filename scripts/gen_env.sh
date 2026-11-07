#!/usr/bin/env bash
# Create .env for the Docker stack with freshly generated secrets.
# Usage: ./scripts/gen_env.sh <domain> <admin-email>
set -euo pipefail

DOMAIN="${1:-}"
ADMIN_EMAIL="${2:-}"
if [ -z "$DOMAIN" ] || [ -z "$ADMIN_EMAIL" ]; then
  echo "Usage: $0 <domain> <admin-email>   e.g. $0 decops.rogan.live admin@example.com" >&2
  exit 1
fi
cd "$(dirname "$0")/.."
if [ -e .env ]; then
  echo ".env already exists - refusing to overwrite it (rotating secrets would lock out existing data)." >&2
  exit 1
fi

ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)Aa1!"
umask 077
sed \
  -e "s|^DOMAIN=.*|DOMAIN=${DOMAIN}|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" \
  -e "s|^DECOPS_SESSION_SECRET_KEY=.*|DECOPS_SESSION_SECRET_KEY=$(openssl rand -hex 32)|" \
  -e "s|^DECOPS_SEED_ADMIN_EMAIL=.*|DECOPS_SEED_ADMIN_EMAIL=${ADMIN_EMAIL}|" \
  -e "s|^DECOPS_SEED_ADMIN_PASSWORD=.*|DECOPS_SEED_ADMIN_PASSWORD=${ADMIN_PASSWORD}|" \
  .env.example > .env

echo "Wrote .env (mode 600)."
echo "Admin login:  ${ADMIN_EMAIL}"
echo "Password:     ${ADMIN_PASSWORD}   <- shown once; change it after first sign-in"
echo "Back up .env somewhere safe: DECOPS_SESSION_SECRET_KEY also protects stored 2FA secrets and webhook secrets."
