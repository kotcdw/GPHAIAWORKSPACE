#!/usr/bin/env bash
# GIAW - install or update on a Linux VPS (Ubuntu/Debian, e.g. a Hostinger KVM VPS).
#
#   sudo bash deploy/vps/install.sh                         (asks for the domain and e-mail)
#   sudo bash deploy/vps/install.sh giaworkspace.com you@example.com
#
# What it does:
#   1. installs Docker if it is missing;
#   2. on the first run, creates .env.production with random passwords and keys (shown ONCE);
#   3. opens only SSH, HTTP and HTTPS in the firewall (ufw), if you agree;
#   4. builds and starts MySQL + GIAW + Caddy, which gets the HTTPS certificate automatically.
# Run it again after "git pull" to update: data, passwords and certificates are kept.
set -euo pipefail

cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
ENV_FILE="$ROOT/.env.production"
COMPOSE=(docker compose -f "$ROOT/deploy/vps/docker-compose.yml" --env-file "$ENV_FILE")

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run with sudo:  sudo bash deploy/vps/install.sh"
[ -f "$ROOT/Dockerfile" ] || die "Run this from the GIAW repository (Dockerfile not found in $ROOT)."

# --------------------------------------------------------------------------- 1. Docker
if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker"
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing. Install the docker-compose-plugin package and run again."
systemctl enable --now docker >/dev/null 2>&1 || true

# --------------------------------------------------------------------------- 2. Settings
rand_hex() { openssl rand -hex "$1"; }
fernet_key() { openssl rand -base64 32 | tr '+/' '-_'; }

if [ ! -f "$ENV_FILE" ]; then
  DOMAIN="${1:-}"
  EMAIL="${2:-}"
  [ -n "$DOMAIN" ] || read -rp "Domain name for GIAW (for example giaworkspace.com): " DOMAIN
  [ -n "$EMAIL" ] || read -rp "Your e-mail (certificate notices and the first admin account): " EMAIL
  DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#www.}"; DOMAIN="${DOMAIN%%/*}"
  [[ "$DOMAIN" == *.* ]] || die "\"$DOMAIN\" does not look like a domain name."
  [[ "$EMAIL" == *@*.* ]] || die "\"$EMAIL\" does not look like an e-mail address."

  ADMIN_PASSWORD="Giaw-$(rand_hex 8)"
  umask 077
  cat > "$ENV_FILE" <<ENV
# GIAW production settings - created by deploy/vps/install.sh on $(date -u +%Y-%m-%d).
# KEEP THIS FILE SECRET. Never e-mail it, paste it in chat or commit it.
# Losing GPHA_ENCRYPTION_KEY makes every uploaded file and backup unreadable:
# keep a copy of this file offline (for example on an encrypted USB key in a safe).
GIAW_DOMAIN=$DOMAIN
GIAW_ACME_EMAIL=$EMAIL

GPHA_ENVIRONMENT=production
GPHA_APP_BASE_URL=https://$DOMAIN
GPHA_COOKIE_SECURE=true
GPHA_API_DOCS=false
GPHA_SECRET_KEY=$(rand_hex 32)
GPHA_ENCRYPTION_KEY=$(fernet_key)

GPHA_MYSQL_DATABASE=gpha_workspace
GPHA_MYSQL_USER=gpha
GPHA_MYSQL_PASSWORD=$(rand_hex 24)
GPHA_MYSQL_ROOT_PASSWORD=$(rand_hex 24)

# First administrator (created on the first start only; change the password after signing in).
GPHA_ADMIN_USERNAME=admin
GPHA_ADMIN_PASSWORD=$ADMIN_PASSWORD
GPHA_ADMIN_EMAIL=$EMAIL
GPHA_ADMIN_FULL_NAME=GIAW Administrator
ENV
  chmod 600 "$ENV_FILE"
  FIRST_RUN=1
else
  FIRST_RUN=0
  say "Using the existing settings in .env.production (passwords and keys unchanged)"
fi

DOMAIN="$(grep -E '^GIAW_DOMAIN=' "$ENV_FILE" | cut -d= -f2-)"

# --------------------------------------------------------------------------- 3. Checks
SERVER_IP="$( (ip -4 route get 1.1.1.1 2>/dev/null || true) | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1)"
DNS_IP="$( (getent ahostsv4 "$DOMAIN" 2>/dev/null || true) | awk 'NR==1{print $1}')"
if [ -n "$SERVER_IP" ] && [ "$DNS_IP" != "$SERVER_IP" ]; then
  warn "DNS check: $DOMAIN points to '${DNS_IP:-nothing}', this server is $SERVER_IP."
  warn "Set an A record:  @ -> $SERVER_IP  (and www -> $DOMAIN as CNAME). HTTPS starts working once DNS has updated."
fi

# A database container from an earlier test deployment (the development docker-compose.yml) blocks nothing,
# but it runs with the published development passwords. Offer to remove it.
if docker ps -a --format '{{.Names}}' | grep -qx 'gpha-mysql'; then
  warn "Found the old test container 'gpha-mysql' (development passwords, not used by this installation)."
  read -rp "Stop and remove it? It holds no GIAW data from this installation. [y/N] " ans
  if [[ "${ans:-n}" =~ ^[Yy]$ ]]; then docker rm -f gpha-mysql >/dev/null && echo "Removed gpha-mysql."; fi
fi

if command -v ufw >/dev/null 2>&1; then
  if ! ufw status | grep -q "Status: active"; then
    read -rp "Turn on the firewall and allow only SSH (22), HTTP (80) and HTTPS (443)? [Y/n] " ans
    if [[ ! "${ans:-y}" =~ ^[Nn]$ ]]; then
      ufw allow OpenSSH >/dev/null 2>&1 || ufw allow 22/tcp >/dev/null
      ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null
      ufw --force enable >/dev/null && echo "Firewall on: 22, 80, 443 open."
    fi
  else
    ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null
  fi
fi

# --------------------------------------------------------------------------- 4. Build and start
say "Building and starting GIAW (the first build takes a few minutes)"
"${COMPOSE[@]}" up -d --build --remove-orphans

say "Waiting for GIAW to answer"
for _ in $(seq 1 60); do
  state="$( ("${COMPOSE[@]}" ps --format '{{.Service}} {{.Health}}' 2>/dev/null || true) | awk '$1=="app"{print $2}')"
  [ "$state" = "healthy" ] && break
  sleep 5
done
"${COMPOSE[@]}" ps
[ "${state:-}" = "healthy" ] || { warn "GIAW is not healthy yet. Look at:  docker compose -f deploy/vps/docker-compose.yml --env-file .env.production logs app"; exit 1; }

echo
printf '\033[1;32m%s\033[0m\n' "GIAW is running:  https://$DOMAIN"
if [ "$FIRST_RUN" = 1 ]; then
  echo
  warn "First administrator - write this down now (it is also in .env.production as GPHA_ADMIN_PASSWORD):"
  echo "    Username: admin"
  echo "    Password: $ADMIN_PASSWORD"
  echo
  warn "Then sign in, change that password, and turn on two-step verification."
  warn "Make an offline copy of $ENV_FILE (it holds the encryption key)."
fi
