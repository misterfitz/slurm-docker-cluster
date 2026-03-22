#!/usr/bin/env bash
# slurm-status.sh — Cached wrapper for tmux status bar integration.
#
# Calls `playground priority tmux-status` and caches the result for
# CACHE_TTL seconds to avoid hammering the cluster on every tmux
# refresh cycle.
#
# Usage in ~/.tmux.conf:
#   set -g status-right '#(/path/to/slurm-status.sh -u user01)'
#   set -g status-interval 10
#
# All arguments are forwarded to `playground priority tmux-status`.

set -euo pipefail

CACHE_TTL="${SLURM_TMUX_CACHE_TTL:-10}"
CACHE_FILE="/tmp/slurm-tmux-status-${USER:-unknown}.cache"

# Serve from cache if fresh enough
if [ -f "$CACHE_FILE" ]; then
    if [[ "$OSTYPE" == darwin* ]]; then
        mod_time=$(stat -f%m "$CACHE_FILE" 2>/dev/null || echo 0)
    else
        mod_time=$(stat -c%Y "$CACHE_FILE" 2>/dev/null || echo 0)
    fi
    now=$(date +%s)
    age=$(( now - mod_time ))
    if [ "$age" -lt "$CACHE_TTL" ]; then
        cat "$CACHE_FILE"
        exit 0
    fi
fi

# Refresh cache
if command -v playground &>/dev/null; then
    playground priority tmux-status "$@" > "$CACHE_FILE" 2>/dev/null || echo "slurm:err" > "$CACHE_FILE"
else
    # Try finding it relative to this script
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PLAYGROUND_CMD="$SCRIPT_DIR/../cli/slurm_playground/main.py"
    if [ -f "$PLAYGROUND_CMD" ]; then
        python3 -m slurm_playground priority tmux-status "$@" > "$CACHE_FILE" 2>/dev/null || echo "slurm:err" > "$CACHE_FILE"
    else
        echo "slurm:?" > "$CACHE_FILE"
    fi
fi

cat "$CACHE_FILE"
