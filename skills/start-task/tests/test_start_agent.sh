#!/usr/bin/env bash
# Tests for scripts/start-agent.sh. Stubs `herdr` with canned pane and agent lists,
# so nothing touches a real Herdr session.
set -uo pipefail

script="$(cd "$(dirname "$0")/.." && pwd -P)/scripts/start-agent.sh"
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
check "brief is sent as the prompt" 'grep -q "^agent prompt mer-63 Task brief" "$log"'
check "prompt waits only until work starts" 'grep -q -- "--until working --until blocked --timeout" "$log"'

# 2. Idle Claude already there: renamed and reused, never a second start.
setup "$idle_claude"
run w9 MER-63 "$sandbox/brief.md"
check "idle claude exits 0" '[ "$rc" -eq 0 ]'
check "idle claude is renamed" 'grep -q "^agent rename w9:p1 mer-63" "$log"'
check "idle claude is not started again" '! grep -q "^agent start" "$log"'
check "idle claude gets the brief" 'grep -q "^agent prompt mer-63" "$log"'

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
check "busy pane gets no prompt" '! grep -q "^agent prompt" "$log"'

# 6. Pane running another agent kind: refuses.
setup '{"pane_id":"w9:p1","agent":"codex","agent_status":"idle"}'
run w9 MER-63 "$sandbox/brief.md"
check "other agent kind exits non-zero" '[ "$rc" -ne 0 ] && ! grep -q "^agent prompt" "$log"'

# 7. Empty brief: refuses before calling herdr.
setup "$shell_pane"
: > "$sandbox/brief.md"
run w9 MER-63 "$sandbox/brief.md"
check "empty brief exits non-zero" '[ "$rc" -ne 0 ] && [ ! -e "$log" ]'

# 8. Outside Herdr: refuses before calling herdr.
setup "$shell_pane"
PATH="$sandbox/bin:$PATH" HERDR_ENV= "$script" w9 MER-63 "$sandbox/brief.md" >"$sandbox/out" 2>&1; rc=$?
check "outside Herdr exits non-zero" '[ "$rc" -ne 0 ] && [ ! -e "$log" ]'

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
