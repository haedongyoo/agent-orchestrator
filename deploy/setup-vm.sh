#!/usr/bin/env bash
# OpenClaw — one-time VM setup for Oracle Cloud ARM instance.
# Run this once after provisioning: ssh ubuntu@<ip> 'bash -s' < deploy/setup-vm.sh
#
# What it does:
#   1. Adds ubuntu user to docker group (avoids sudo for docker)
#   2. Clones the repo
#   3. Generates .env with secure random secrets
#   4. Prints next steps

set -euo pipefail

APP_DIR="$HOME/agent-orchestrator"

echo "==> Setting up OpenClaw on $(hostname)..."

# ── Docker group ────────────────────────────────────────────────────────────
if ! groups | grep -q docker; then
    echo "==> Adding $USER to docker group..."
    sudo usermod -aG docker "$USER"
    echo "NOTE: You'll need to log out and back in for docker group to take effect."
    echo "      Or run: newgrp docker"
fi

# ── Clone repo ──────────────────────────────────────────────────────────────
if [ ! -d "$APP_DIR" ]; then
    echo "==> Cloning repository..."
    git clone https://github.com/haedongyoo/agent-orchestrator.git "$APP_DIR"
else
    echo "==> Repo already exists at $APP_DIR"
fi

cd "$APP_DIR"

# ── Generate .env ───────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    echo "==> Generating .env with secure random secrets..."
    cp .env.example .env

    # Generate secure random values
    SECRET_KEY=$(openssl rand -hex 32)
    POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
    REDIS_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || openssl rand -base64 32)

    # Apply to .env
    sed -i "s|SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" .env
    sed -i "s|ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$ENCRYPTION_KEY|" .env

    # Add production-only vars
    cat >> .env <<EOF

# ── Production secrets (auto-generated) ─────────────────────────────────────
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
REDIS_PASSWORD=$REDIS_PASSWORD
ALLOWED_ORIGINS=http://150.230.183.145,http://localhost
NEXT_PUBLIC_API_URL=http://150.230.183.145
NEXT_PUBLIC_WS_URL=ws://150.230.183.145
APP_ENV=production
LOG_LEVEL=info
EOF

    echo "==> .env created. Edit it to add your LLM_API_KEY:"
    echo "    nano $APP_DIR/.env"
else
    echo "==> .env already exists, skipping generation"
fi

echo ""
echo "============================================"
echo "  VM setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Log out and back in (for docker group)"
echo "  2. Edit .env to set LLM_API_KEY:"
echo "     nano $APP_DIR/.env"
echo "  3. Deploy:"
echo "     cd $APP_DIR && bash deploy/deploy.sh"
echo ""
