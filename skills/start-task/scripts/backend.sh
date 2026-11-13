# Sourced by the start-task scripts: which Herdr this session runs inside.
#   tui  Herdr TUI (`herdr`, 0.9+): sets HERDR_ENV=1 in its panes.
#   app  Herdr app (`herdr-app` over herdr-core's `hc`): sets HC_TERMINAL_ID in its terminals.
# The two run separate servers and share no workspaces or agents.
herdr_backend() {
  if [ "${HERDR_ENV:-}" = 1 ]; then
    echo tui
  elif [ -n "${HC_TERMINAL_ID:-}" ] && command -v herdr-app >/dev/null && command -v hc >/dev/null; then
    echo app
  else
    echo "error: not running inside Herdr (neither a TUI pane nor an app terminal)" >&2
    return 1
  fi
}
