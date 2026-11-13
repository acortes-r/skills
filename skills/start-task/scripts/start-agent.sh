#!/usr/bin/env bash
# Put a coding agent in a workspace's first pane and point it at a task brief.
# Usage: start-agent.sh <workspace-id> <agent-name> <brief-file> [kind]
# Works in Herdr TUI (workspace, pane) and in the Herdr app (space, terminal); see backend.sh.
# kind is a Herdr agent kind (claude, codex, cursor, …): the argument, else
# $START_TASK_AGENT, else claude.
# Reuses an idle agent of that kind already in the pane; otherwise starts one in the shell.
# The agent gets a one-line prompt naming the brief file, never the brief itself.
# Prints the agent's JSON: TUI `herdr agent get` (agent_status), app `hc get` (status.state).
set -euo pipefail
# shellcheck source=backend.sh
. "$(dirname "$0")/backend.sh"

usage="usage: start-agent.sh <workspace-id> <agent-name> <brief-file> [kind]"
workspace="${1:?$usage}"
wanted="${2:?$usage}"
brief="${3:?$usage}"
kind="${4:-${START_TASK_AGENT:-claude}}"

backend="$(herdr_backend)" || exit 1
[[ "$kind" =~ ^[a-z][a-z0-9_-]*$ ]] || { echo "error: invalid agent kind: $kind" >&2; exit 1; }
[ -s "$brief" ] || { echo "error: brief file missing or empty: $brief" >&2; exit 1; }
brief="$(cd "$(dirname "$brief")" && pwd -P)/$(basename "$brief")"
prompt="Read the task brief in $brief and start on it."

if [ "$backend" = app ]; then
  # The space's first terminal, and what runs in it: shell name, agent app, agent state.
  term="$(herdr-app ls | python3 -c '
import json, sys
for s in json.load(sys.stdin)["spaces"]:
    if s["id"] == sys.argv[1]:
        terms = [t for tab in s["tabs"] for t in tab["terminals"]]
        if not terms:
            sys.exit("error: space has no terminals")
        print(terms[0]["terminal"]); break
else:
    sys.exit("error: no such space: " + sys.argv[1])
' "$workspace")"
  read -r fg app state <<<"$(hc get "$term" | python3 -c '
import json, os, sys
t = json.load(sys.stdin)
st = t.get("status") or {}
fg = ((t.get("foreground") or {}).get("argv") or ["-"])[0]
print(os.path.basename(fg).lstrip("-") or "-", st.get("app") or "-", st.get("state") or "-")
')"
  # herdr-core reports Claude Code as claude-code; other agents by their own name.
  [ "$kind" = claude ] && app_name=claude-code || app_name="$kind"

  if [ "$app" = "-" ] && [[ "$fg" =~ ^(sh|bash|zsh|fish|dash|ksh)$ ]]; then
    # Shell at the prompt: type the launch, the prompt riding on its command line.
    hc send "$term" "$kind $(python3 -c 'import shlex, sys; print(shlex.quote(sys.argv[1]))' "$prompt")" >/dev/null
    started='^(working|blocked|done)$'  # a fresh agent only reaches done by finishing the brief
  elif [ "$app" = "$app_name" ] && { [ "$state" = idle ] || [ "$state" = done ]; }; then
    hc send "$term" "$prompt" >/dev/null
    started='^(working|blocked)$'       # done is the previous turn's
  else
    echo "error: terminal $term is busy: $( [ "$app" = - ] && echo "$fg" || echo "$app" ) ($state)" >&2
    exit 1
  fi

  # Wait until the prompt is taken up, not for the whole turn; a trust or permission
  # dialog leaves it blocked. On a timeout the printed status still says where it stands.
  for _ in $(seq 60); do
    state="$(hc get "$term" | python3 -c 'import json, sys; print((json.load(sys.stdin).get("status") or {}).get("state") or "-")')"
    [[ "$state" =~ $started ]] && break
    sleep 1
  done
  hc get "$term"
  exit 0
fi

# Fields of the workspace's first pane: pane_id, agent kind, agent status, agent name.
read -r pane agent status current <<<"$(herdr pane list --workspace "$workspace" | python3 -c '
import json, sys
panes = json.load(sys.stdin)["result"]["panes"]
if not panes:
    sys.exit("error: workspace has no panes")
p = panes[0]
print(p["pane_id"], p.get("agent") or "-", p.get("agent_status") or "-", p.get("name") or p.get("agent_name") or "-")
')"

# Herdr names: [a-z][a-z0-9_-]{0,31}, unique among live agents. Suffix -2, -3, … on a clash.
name="$(herdr agent list | python3 -c '
import json, re, sys
wanted, current = sys.argv[1], sys.argv[2]
base = re.sub(r"[^a-z0-9_-]+", "-", wanted.lower()).strip("-")
if not base or not base[0].isalpha():
    base = "t-" + base
base = base[:32]
agents = json.load(sys.stdin)["result"]["agents"]
taken = {a.get("name") or a.get("agent_name") for a in agents} - {current}
name, n = base, 2
while name in taken:
    suffix = f"-{n}"
    name, n = base[:32 - len(suffix)] + suffix, n + 1
print(name)
' "$wanted" "$current")"

# Wait until the prompt is taken up, not for the whole turn; a trust or permission
# dialog leaves it blocked. On a timeout the printed status still says where it stands.
until_started=(--until working --until blocked --timeout 30000)

if [ "$agent" = "-" ]; then
  # The prompt rides on the command line, so nothing is typed into a dialog.
  herdr agent start "$name" --kind "$kind" --pane "$pane" --timeout 60000 -- "$prompt" >/dev/null
  # A fresh agent can only reach done by finishing the brief's turn.
  herdr agent wait "$name" "${until_started[@]}" --until done >/dev/null || true
elif [ "$agent" = "$kind" ] && { [ "$status" = idle ] || [ "$status" = done ]; }; then
  [ "$current" = "$name" ] || herdr agent rename "$pane" "$name" >/dev/null
  herdr agent prompt "$name" "$prompt" --wait "${until_started[@]}" >/dev/null || true
else
  echo "error: pane $pane is busy: $agent ($status)" >&2
  exit 1
fi

herdr agent get "$name"
