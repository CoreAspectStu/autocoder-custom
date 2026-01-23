#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

TMUX_SESSION_PREFIX="autocoder"
UI_SESSION="${TMUX_SESSION_PREFIX}-ui"
DISPLAY_NUM=99
XVFB_PID_FILE="/tmp/autocoder-xvfb.pid"

LOG_DIR="$SCRIPT_DIR/logs"
UI_LOG="$LOG_DIR/autocoder-ui.log"

FOREGROUND="${AUTOCODER_FOREGROUND:-0}"

# Parse flags
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --foreground) FOREGROUND="1" ;;
    *) ARGS+=("$arg") ;;
  esac
done
set -- "${ARGS[@]:-}"

die() { echo "ERROR: $*" >&2; exit 1; }

ensure_deps() {
  command -v tmux >/dev/null 2>&1 || die "tmux missing (sudo apt-get install -y tmux)"
  command -v python3 >/dev/null 2>&1 || die "python3 missing"
}

start_xvfb() {
  mkdir -p "$LOG_DIR"

  if [[ -f "$XVFB_PID_FILE" ]]; then
    pid="$(cat "$XVFB_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      export DISPLAY=":${DISPLAY_NUM}"
      return 0
    fi
    rm -f "$XVFB_PID_FILE"
  fi

  if pgrep -af "Xvfb :${DISPLAY_NUM}\b" >/dev/null 2>&1; then
    export DISPLAY=":${DISPLAY_NUM}"
    return 0
  fi

  nohup Xvfb ":${DISPLAY_NUM}" -screen 0 1920x1080x24 >"$LOG_DIR/xvfb.log" 2>&1 &
  echo "$!" > "$XVFB_PID_FILE"
  export DISPLAY=":${DISPLAY_NUM}"
}

stop_xvfb() {
  if [[ -f "$XVFB_PID_FILE" ]]; then
    pid="$(cat "$XVFB_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$XVFB_PID_FILE"
  else
    pkill -f "Xvfb :${DISPLAY_NUM}\b" 2>/dev/null || true
  fi
}

ui_cmd() {
  # Your known-good UI command (from your tmux output)
  echo "uvicorn server.main:app --host 127.0.0.1 --port 8888"
}

stop_all() {
  ensure_deps

  # Kill tmux autocoder sessions
  if tmux ls >/dev/null 2>&1; then
    tmux ls | awk -F: '{print $1}' | grep -E "^${TMUX_SESSION_PREFIX}-" | while read -r s; do
      tmux kill-session -t "$s" 2>/dev/null || true
    done
  fi

  # Kill any process holding 8888 (psmisc provides fuser)
  command -v fuser >/dev/null 2>&1 && fuser -k 8888/tcp 2>/dev/null || true

  # Best-effort cleanup
  pkill -f "playwright_chromiumdev_profile-" 2>/dev/null || true
  pkill -f "@playwright/mcp" 2>/dev/null || true
  pkill -f "^claude$" 2>/dev/null || true

  stop_xvfb
  echo "Stopped."
}

status() {
  ensure_deps
  tmux ls 2>/dev/null || echo "(no tmux sessions)"
  ss -ltnp 2>/dev/null | grep ':8888' || echo "(8888 not listening)"
}

logs() {
  name="${1:-}"; [[ -n "$name" ]] || die "logs needs: ui"
  [[ "$name" == "ui" ]] || die "only supported: logs ui"
  [[ -f "$UI_LOG" ]] || die "no log file: $UI_LOG"
  exec tail -n 200 -F "$UI_LOG"
}

attach() {
  name="${1:-}"; [[ -n "$name" ]] || die "attach needs: ui"
  [[ "$name" == "ui" ]] || die "only supported: attach ui"
  tmux has-session -t "$UI_SESSION" 2>/dev/null || die "session not running: $UI_SESSION"
  exec tmux attach -t "$UI_SESSION"
}

start_ui() {
  ensure_deps
  mkdir -p "$LOG_DIR"
  start_xvfb

  export PLAYWRIGHT_HEADLESS=false

  if [[ -f "$SCRIPT_DIR/venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/venv/bin/activate"
  fi

  CMD="$(ui_cmd)"

  if [[ "$FOREGROUND" == "1" ]]; then
    exec "$SCRIPT_DIR/venv/bin/python" -m $CMD 2>&1 | tee -a "$UI_LOG"
  fi

  # Detached mode via tmux
  tmux has-session -t "$UI_SESSION" 2>/dev/null || \
    tmux new-session -d -s "$UI_SESSION" -c "$SCRIPT_DIR" \
      "bash -lc 'export DISPLAY=:$DISPLAY_NUM; export PLAYWRIGHT_HEADLESS=false; \
      if [ -f venv/bin/activate ]; then source venv/bin/activate; fi; \
      $CMD 2>&1 | tee -a \"$UI_LOG\"'"

  echo "UI session: $UI_SESSION"
  echo "Logs: $UI_LOG"
  echo "Attach: tmux attach -t $UI_SESSION"
}

usage() {
  cat <<USAGE
Usage:
  ./remote-start.sh ui [--foreground]
  ./remote-start.sh status
  ./remote-start.sh stop
  ./remote-start.sh logs ui
  ./remote-start.sh attach ui
USAGE
}

main() {
  cmd="${1:-}"; shift || true
  case "$cmd" in
    ui) start_ui ;;
    status) status ;;
    stop) stop_all ;;
    logs) logs "${1:-}" ;;
    attach) attach "${1:-}" ;;
    ""|-h|--help|help) usage ;;
    *) usage; die "unknown command: $cmd" ;;
  esac
}

main "$@"
