#!/usr/bin/env bash
# start.sh — runs every time the service starts on Render

set -e

# Render containers need /dev/net/tun for Tailscale
if [ ! -c /dev/net/tun ]; then
    mkdir -p /dev/net
    mknod /dev/net/tun c 10 200
    chmod 600 /dev/net/tun
fi

# Run the bot (tailscale up is called inside main() via start_tailscale())
exec python bot.py
