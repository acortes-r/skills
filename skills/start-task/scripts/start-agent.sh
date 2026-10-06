#!/usr/bin/env bash
# Put a Claude agent in a workspace's first pane and hand it a task brief.
# Usage: start-agent.sh <workspace-id> <agent-name> <brief-file>
# Reuses an idle Claude already in that pane; otherwise starts one in the shell.
# Prints the Herdr JSON for the agent on success.
set -euo pipefail

usage="usage: start-agent.sh <workspace-id> <agent-name> <brief-file>"
workspace="${1:?$usage}"
wanted="${2:?$usage}"
brief="${3:?$usage}"

[ "${HERDR_ENV:-}" = 1 ] || { echo "error: not running inside a Herdr pane" >&2; exit 1; }
[ -s "$brief" ] || { echo "error: brief file missing or empty: $brief" >&2; exit 1; }

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

if [ "$agent" = "-" ]; then
  herdr agent start "$name" --kind claude --pane "$pane" --timeout 60000 >/dev/null
elif [ "$agent" = claude ] && { [ "$status" = idle ] || [ "$status" = done ]; }; then
  [ "$current" = "$name" ] || herdr agent rename "$pane" "$name" >/dev/null
else
  echo "error: pane $pane is busy: $agent ($status)" >&2
  exit 1
fi

# Confirm the brief was taken up without waiting for the whole turn.
herdr agent prompt "$name" "$(cat "$brief")" --wait --until working --until blocked --timeout 30000 >/dev/null
herdr agent get "$name"
