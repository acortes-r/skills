#!/usr/bin/env bash
# Tests for scripts/start-agent.sh. Stubs `herdr` with canned pane and agent lists,
# so nothing touches a real Herdr session.
set -uo pipefail

script="$(cd "$(dirname "$0")/.." && pwd -P)/scripts/start-agent.sh"
unset START_TASK_AGENT HERDR_ENV HC_TERMINAL_ID  # tests set them explicitly; the shell's would skew them
pass=0
fail=0

ok()   { pass=$((pass + 1)); echo "ok   - $1"; }
nok()  { fail=$((fail + 1)); echo "FAIL - $1"; [ -n "${2:-}" ] && echo "       $2"; }
check() { if eval "$2"; then ok "$1"; else nok "$1" "$2"; fi; }

sandboxes=()
trap 'rm -rf "${sandboxes[@]}"' EXIT

# setup <first-pane-json> [agent-list-json]
setup() {
  sandbox="$(cd "$(mktemp -d)" && pwd -P)"
  sandboxes+=("$sandbox")
  log="$sandbox/herdr.log"
  printf '{"result":{"panes":[%s]}}' "$1" > "$sandbox/panes.json"
  printf '{"result":{"agents":[%s]}}' "${2:-}" > "$sandbox/agents.json"
  printf 'Task brief\nline two\n' > "$sandbox/brief.md"
  mkdir -p "$sandbox/bin"
  cat > "$sandbox/bin/herdr" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$log"
case "\$1 \$2" in
  "pane list")  cat "$sandbox/panes.json" ;;
  "agent list") cat "$sandbox/agents.json" ;;
  *)            echo '{"result":{"stub":true}}' ;;
esac
EOF
  chmod +x "$sandbox/bin/herdr"
}

run() { PATH="$sandbox/bin:$PATH" HERDR_ENV=1 "$script" "$@" >"$sandbox/out" 2>&1; rc=$?; }

shell_pane='{"pane_id":"w9:p1","agent_status":"unknown"}'
idle_claude='{"pane_id":"w9:p1","agent":"claude","agent_status":"idle"}'

# 1. Shell at the prompt: starts Claude there, then prompts it with the brief.
setup "$shell_pane"
run w9 MER-63 "$sandbox/brief.md"
check "shell pane exits 0" '[ "$rc" -eq 0 ]'
check "shell pane starts claude in the first pane" 'grep -q "^agent start mer-63 --kind claude --pane w9:p1" "$log"'
check "start carries a one-line prompt naming the brief" 'grep -qF -- "-- Read the task brief in $sandbox/brief.md and start on it." "$log"'
check "brief text itself is never sent" '! grep -q "Task brief" "$log"'
check "start is not followed by a typed prompt" '! grep -q "^agent prompt" "$log"'
check "start waits only until work starts" 'grep -q "^agent wait mer-63 --until working --until blocked --timeout 30000 --until done" "$log"'

# 2. Idle Claude already there: renamed and reused, never a second start.
setup "$idle_claude"
run w9 MER-63 "$sandbox/brief.md"
check "idle claude exits 0" '[ "$rc" -eq 0 ]'
check "idle claude is renamed" 'grep -q "^agent rename w9:p1 mer-63" "$log"'
check "idle claude is not started again" '! grep -q "^agent start" "$log"'
check "idle claude is prompted with the brief path" 'grep -qF "agent prompt mer-63 Read the task brief in $sandbox/brief.md" "$log"'
check "prompt waits until work starts, not on the old done" 'grep -q -- "--wait --until working --until blocked --timeout 30000$" "$log"'

# 3. Name taken by another live agent: suffixed.
setup "$shell_pane" '{"pane_id":"w2:p1","agent":"claude","name":"mer-63"}'
run w9 MER-63 "$sandbox/brief.md"
check "name clash gets a suffix" 'grep -q "^agent start mer-63-2 " "$log"'

# 4. Label that is not a valid Herdr name: normalized.
setup "$shell_pane"
run w9 "fix/Rapido Discount" "$sandbox/brief.md"
check "label normalized to a herdr name" 'grep -q "^agent start fix-rapido-discount " "$log"'

# 5. Pane busy with a working agent: refuses, sends nothing.
setup '{"pane_id":"w9:p1","agent":"claude","agent_status":"working"}'
run w9 MER-63 "$sandbox/brief.md"
check "busy pane exits non-zero" '[ "$rc" -ne 0 ]'
check "busy pane gets no prompt" '! grep -q "^agent prompt" "$log" && ! grep -q "^agent start" "$log"'

# 6. Pane running another agent kind than the default claude: refuses.
setup '{"pane_id":"w9:p1","agent":"codex","agent_status":"idle"}'
run w9 MER-63 "$sandbox/brief.md"
check "other agent kind exits non-zero" '[ "$rc" -ne 0 ] && ! grep -q "^agent prompt" "$log"'

# 7. Empty brief: refuses before calling herdr.
setup "$shell_pane"
: > "$sandbox/brief.md"
run w9 MER-63 "$sandbox/brief.md"
check "empty brief exits non-zero" '[ "$rc" -ne 0 ] && [ ! -e "$log" ]'

# 8. Relative brief path: the prompt names it absolutely.
setup "$shell_pane"
(cd "$sandbox" && PATH="$sandbox/bin:$PATH" HERDR_ENV=1 "$script" w9 MER-63 brief.md) >"$sandbox/out" 2>&1; rc=$?
check "relative brief path is made absolute" '[ "$rc" -eq 0 ] && grep -qF "Read the task brief in $sandbox/brief.md" "$log"'

# 9. Kind as an argument: starts that agent.
setup "$shell_pane"
run w9 MER-63 "$sandbox/brief.md" codex
check "codex kind exits 0" '[ "$rc" -eq 0 ]'
check "codex kind starts codex" 'grep -q "^agent start mer-63 --kind codex --pane w9:p1 --timeout 60000 -- Read the task brief" "$log"'

# 10. Kind from START_TASK_AGENT when no argument names one.
setup "$shell_pane"
PATH="$sandbox/bin:$PATH" HERDR_ENV=1 START_TASK_AGENT=cursor "$script" w9 MER-63 "$sandbox/brief.md" >"$sandbox/out" 2>&1; rc=$?
check "START_TASK_AGENT sets the kind" '[ "$rc" -eq 0 ] && grep -q "^agent start mer-63 --kind cursor " "$log"'

# 11. The argument wins over START_TASK_AGENT.
setup "$shell_pane"
PATH="$sandbox/bin:$PATH" HERDR_ENV=1 START_TASK_AGENT=cursor "$script" w9 MER-63 "$sandbox/brief.md" codex >"$sandbox/out" 2>&1; rc=$?
check "argument overrides START_TASK_AGENT" 'grep -q "^agent start mer-63 --kind codex " "$log"'

# 12. Idle agent of the asked kind: reused.
setup '{"pane_id":"w9:p1","agent":"codex","agent_status":"idle"}'
run w9 MER-63 "$sandbox/brief.md" codex
check "idle codex is reused for codex" '[ "$rc" -eq 0 ] && ! grep -q "^agent start" "$log" && grep -q "^agent prompt mer-63 Read the task brief" "$log"'

# 13. Idle agent of another kind: refuses.
setup "$idle_claude"
run w9 MER-63 "$sandbox/brief.md" codex
check "idle claude refused when codex is asked" '[ "$rc" -ne 0 ] && ! grep -q "^agent prompt" "$log"'

# 14. Malformed kind: refuses before calling herdr.
setup "$shell_pane"
run w9 MER-63 "$sandbox/brief.md" "Codex; rm"
check "malformed kind exits non-zero" '[ "$rc" -ne 0 ] && [ ! -e "$log" ]'

# 15. Outside Herdr: refuses before calling herdr.
setup "$shell_pane"
PATH="$sandbox/bin:$PATH" HERDR_ENV= "$script" w9 MER-63 "$sandbox/brief.md" >"$sandbox/out" 2>&1; rc=$?
check "outside Herdr exits non-zero" '[ "$rc" -ne 0 ] && [ ! -e "$log" ]'

# --- Herdr app backend: herdr-app and hc stubbed ---

# setup_app <terminal-get-json>: space spW whose first terminal is t9. A send flips
# t9 to working, as the agent taking the prompt would.
setup_app() {
  sandbox="$(cd "$(mktemp -d)" && pwd -P)"
  sandboxes+=("$sandbox")
  log="$sandbox/app.log"
  printf '%s' "$1" > "$sandbox/get.json"
  printf 'Task brief\nline two\n' > "$sandbox/brief.md"
  mkdir -p "$sandbox/bin"
  cat > "$sandbox/bin/herdr-app" <<EOF
#!/usr/bin/env bash
echo "app \$*" >> "$log"
echo '{"spaces":[{"id":"spW","tabs":[{"terminals":[{"terminal":"t9"},{"terminal":"t10"}]}]}]}'
EOF
  cat > "$sandbox/bin/hc" <<EOF
#!/usr/bin/env bash
printf 'hc %s\n' "\$*" >> "$log"
case "\$1" in
  get)  cat "$sandbox/get.json" ;;
  send) echo '{"address":"t9","status":{"app":"x","state":"working"}}' > "$sandbox/get.json"; echo '{}' ;;
esac
EOF
  chmod +x "$sandbox/bin/herdr-app" "$sandbox/bin/hc"
}

run_app() { PATH="$sandbox/bin:$PATH" HC_TERMINAL_ID=t7 "$script" "$@" >"$sandbox/out" 2>&1; rc=$?; }

app_shell='{"address":"t9","foreground":{"argv":["/bin/zsh","-l"]},"status":null}'
app_idle_claude='{"address":"t9","foreground":{"argv":["claude"]},"status":{"app":"claude-code","state":"idle"}}'

# 16. App shell at the prompt: the launch is typed into the space's first terminal.
setup_app "$app_shell"
run_app spW MER-63 "$sandbox/brief.md"
check "app shell exits 0" '[ "$rc" -eq 0 ]'
check "app shell types claude with the quoted prompt" 'grep -qF "hc send t9 claude '"'"'Read the task brief in $sandbox/brief.md and start on it.'"'"'" "$log"'
check "app brief text itself is never sent" '! grep -q "Task brief" "$log"'
check "app prints the terminal once it works" 'grep -q "\"state\":\"working\"" "$sandbox/out"'

# 17. App idle Claude Code: prompted in place, nothing typed into a shell.
setup_app "$app_idle_claude"
run_app spW MER-63 "$sandbox/brief.md"
check "app idle claude is prompted with the brief path" '[ "$rc" -eq 0 ] && grep -qF "hc send t9 Read the task brief in $sandbox/brief.md" "$log"'

# 18. App busy agent: refuses, sends nothing.
setup_app '{"address":"t9","foreground":{"argv":["claude"]},"status":{"app":"claude-code","state":"working"}}'
run_app spW MER-63 "$sandbox/brief.md"
check "app busy terminal exits non-zero" '[ "$rc" -ne 0 ] && ! grep -q "^hc send" "$log"'

# 19. App program that is not a shell nor an agent: refuses.
setup_app '{"address":"t9","foreground":{"argv":["vim"]},"status":null}'
run_app spW MER-63 "$sandbox/brief.md"
check "app foreign program exits non-zero" '[ "$rc" -ne 0 ] && ! grep -q "^hc send" "$log"'

# 20. App with codex asked: types codex; an idle Claude Code is refused for it.
setup_app "$app_shell"
run_app spW MER-63 "$sandbox/brief.md" codex
check "app codex kind types codex" 'grep -qF "hc send t9 codex '"'"'Read the task brief" "$log"'
setup_app "$app_idle_claude"
run_app spW MER-63 "$sandbox/brief.md" codex
check "app idle claude refused when codex is asked" '[ "$rc" -ne 0 ] && ! grep -q "^hc send" "$log"'

# 21. App unknown space: refuses.
setup_app "$app_shell"
run_app spNOPE MER-63 "$sandbox/brief.md"
check "app unknown space exits non-zero" '[ "$rc" -ne 0 ] && ! grep -q "^hc send" "$log"'

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
