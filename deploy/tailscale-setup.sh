#!/usr/bin/env bash
# Tailscale on a server (ADR-051): SSH only over the private Tailscale network, not from the
# internet. Run on each server as a user with sudo, in two steps:
#
#   bash tailscale-setup.sh join <name>     # installs Tailscale, prints a link to add the server
#   bash tailscale-setup.sh lock            # after `ssh <user>@<name>` works over Tailscale:
#                                           # closes port 22 for the internet
#
# Undo the lock (from the server's web console at the provider, if ever needed):
#   sudo ufw allow OpenSSH
set -euo pipefail

case "${1:-}" in
join)
  name=${2:?give the server a name, for example cover-server}
  if ! command -v tailscale >/dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sudo sh
  fi
  sudo systemctl enable --now tailscaled
  echo "Open the link below and approve the server; then test: ssh $USER@$name"
  sudo tailscale up --ssh --hostname "$name"
  tailscale ip -4
  ;;
lock)
  tailscale status >/dev/null || { echo "Tailscale is not up: run 'join' first"; exit 1; }
  sudo ufw allow in on tailscale0 comment 'everything over the Tailscale network'
  sudo ufw delete allow OpenSSH 2>/dev/null || true
  sudo ufw delete allow 22/tcp 2>/dev/null || true
  sudo ufw status verbose
  echo "SSH from the internet is closed; over Tailscale it stays open."
  ;;
*)
  echo "usage: $0 join <name> | lock"
  exit 2
  ;;
esac
