#!/usr/bin/env bash
# =============================================================================
# One-time host bootstrap for sales-ai-agent production server
# Target: fresh Debian 12 / Ubuntu 24.04 LTS
#
# Usage (as root or user with sudo):
#   bash prod/setup-server.sh
# =============================================================================

set -euo pipefail

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
err()  { echo -e "${RED}[error]${NC} $*"; exit 1; }

# --- Pre-flight: must be root or have sudo ---
if [[ $EUID -ne 0 ]]; then
    if ! command -v sudo &>/dev/null; then
        err "This script must be run as root or a user with sudo installed."
    fi
    SUDO="sudo"
else
    SUDO=""
fi

log "Updating package index..."
$SUDO apt-get update -qq

# --- Install system dependencies ---
log "Installing system packages..."
$SUDO apt-get install -y -qq \
    make \
    gettext-base \
    git \
    openssl \
    ca-certificates \
    curl \
    gnupg \
    ufw

# --- Install Docker if missing ---
if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | $SUDO sh
else
    log "Docker already installed: $(docker --version)"
fi

# --- Verify Docker Compose plugin ---
if ! docker compose version &>/dev/null; then
    err "Docker Compose plugin not found. Install it and re-run this script."
fi
log "Docker Compose: $(docker compose version)"

# --- Add current user to docker group ---
if [[ $EUID -ne 0 ]]; then
    DEPLOY_USER="$USER"
else
    # Running as root — try to find the real user
    DEPLOY_USER="${SUDO_USER:-root}"
fi

if [[ "$DEPLOY_USER" != "root" ]]; then
    if groups "$DEPLOY_USER" | grep -qv docker; then
        log "Adding $DEPLOY_USER to docker group..."
        $SUDO usermod -aG docker "$DEPLOY_USER"
        warn "User $DEPLOY_USER added to docker group."
        warn "You MUST log out and back in (or run 'newgrp docker') for this to take effect."
    else
        log "User $DEPLOY_USER already in docker group."
    fi
fi

# --- Configure firewall (UFW) ---
log "Configuring UFW firewall..."
$SUDO ufw --force reset > /dev/null
$SUDO ufw default deny incoming
$SUDO ufw default allow outgoing
$SUDO ufw limit ssh
$SUDO ufw allow http
$SUDO ufw allow https
$SUDO ufw --force enable

log "UFW status:"
$SUDO ufw status verbose

# --- Create external Docker network ---
if ! $SUDO docker network inspect sales-ai-network &>/dev/null; then
    log "Creating external Docker network 'sales-ai-network'..."
    $SUDO docker network create sales-ai-network
else
    log "Docker network 'sales-ai-network' already exists."
fi

# --- Done ---
echo ""
log "=============================================="
log "  Server bootstrap complete!"
log "=============================================="
echo ""
echo "Next steps:"
echo "  1. Clone the repo (if not already done):"
echo "     git clone <repo-url> /opt/sales-ai-agent"
echo "     cd /opt/sales-ai-agent"
echo ""
echo "  2. Create production env file:"
echo "     cp prod/.env.example prod/.env"
echo "     # Edit prod/.env with real values"
echo ""
echo "  2.5. Login to GHCR to be able to pull the app image:"
echo "     echo \$GHCR_TOKEN | docker login ghcr.io -u TU_USUARIO_GITHUB --password-stdin"
echo ""
echo "  3. Initial deploy:"
echo "     make prod-setup"
echo ""
echo "  4. Bootstrap TLS:"
echo "     make ssl-init"
echo ""
echo "  5. Check status:"
echo "     make prod-status"
echo ""
if [[ "$DEPLOY_USER" != "root" ]]; then
    warn "If this is your first time, log out and back in for docker group changes."
fi
