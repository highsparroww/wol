#!/usr/bin/env bash
# build.sh — runs once at deploy time on Render

set -e

# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

echo "Tailscale installed: $(tailscale version)"
