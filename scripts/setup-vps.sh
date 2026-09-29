#!/usr/bin/env bash
# Bootstrap a fresh Ubuntu 24.04 VPS (e.g. Hetzner) for the cover pattern engine + Claude Code.
#
# Run once as root:   bash setup-vps.sh
# Then log in as the dev user, clone or copy this repository, and start `claude` inside tmux.
#
# Sizing: 4 vCPU / 8 GB RAM is enough to develop; 8 vCPU / 16 GB makes hull computation on
# large detailed models noticeably faster. An 8 GB swap file is added as a safety margin.

set -euo pipefail

DEV_USER="${DEV_USER:-dev}"
NODE_MAJOR="${NODE_MAJOR:-22}"
SWAP_GB="${SWAP_GB:-8}"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y upgrade

# ---- Toolchain, Python 3.12 (Ubuntu 24.04 default), headless GL/Qt runtime for OCP/pymeshlab -----
apt-get install -y \
  build-essential cmake ninja-build pkg-config \
  git git-lfs curl wget unzip zip jq rclone \
  python3 python3-venv python3-pip python3-dev \
  libgl1 libglu1-mesa libegl1 libxrender1 libxext6 libxi6 libxkbcommon0 \
  libglib2.0-0 libdbus-1-3 libfontconfig1 libsm6 libice6 \
  tmux htop ufw fail2ban

# ---- Node.js: Claude Code and the Vite front end ---------------------------------------------------
curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
apt-get install -y nodejs
# Claude Code install options change; see https://docs.claude.com/en/docs/claude-code/overview
npm install -g @anthropic-ai/claude-code

# ---- Docker + Compose plugin (deployment of api, web and cloudflared) ---------------------------------
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

# ---- Swap -------------------------------------------------------------------------------------------
if ! swapon --show | grep -q '/swapfile'; then
  fallocate -l "${SWAP_GB}G" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---- Non-root dev user with docker access and root's SSH keys ------------------------------------
if ! id "$DEV_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEV_USER"
  usermod -aG sudo,docker "$DEV_USER"
  echo "$DEV_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$DEV_USER"
  chmod 440 "/etc/sudoers.d/$DEV_USER"
  install -d -m 700 -o "$DEV_USER" -g "$DEV_USER" "/home/$DEV_USER/.ssh"
  if [[ -f /root/.ssh/authorized_keys ]]; then
    install -m 600 -o "$DEV_USER" -g "$DEV_USER" /root/.ssh/authorized_keys "/home/$DEV_USER/.ssh/authorized_keys"
  fi
fi

# ---- Firewall: SSH only. The web app is reached through a Cloudflare Tunnel, never an open port. ---
ufw allow OpenSSH
ufw --force enable
systemctl enable --now fail2ban

# ---- uv (Python project and virtualenv manager) for the dev user ------------------------------------
sudo -u "$DEV_USER" -H bash <<'EOF'
set -euo pipefail
if ! command -v uv >/dev/null 2>&1 && [[ ! -x "$HOME/.local/bin/uv" ]]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
grep -q '.local/bin' "$HOME/.bashrc" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
mkdir -p "$HOME/data"
EOF

cat <<EOF

Done. Next steps:

  ssh ${DEV_USER}@<server-ip>
  git clone <your-repo-url> cover-pattern-engine     # or: scp the scaffold zip and unzip it
  cd cover-pattern-engine
  tmux new -s cover                                  # keeps the session alive if SSH drops
  claude                                             # log in with your Claude subscription,
                                                     # or export ANTHROPIC_API_KEY first

Then paste the prompt from docs/KICKOFF_PROMPT.md.

Cloudflare: create the Tunnel and the Access application in the Zero Trust dashboard when M6
starts; the tunnel token goes into deploy/.env (git-ignored). Use a GitHub token limited to this
repository and an R2 API token limited to the backup bucket.
EOF
