#!/usr/bin/env bash
# Tests for scripts/start-worktree.sh. Builds throwaway git repos and stubs `herdr`,
# so nothing touches a real Herdr session or the network.
set -uo pipefail

script="$(cd "$(dirname "$0")/.." && pwd -P)/scripts/start-worktree.sh"
pass=0
fail=0

ok()   { pass=$((pass + 1)); echo "ok   - $1"; }
nok()  { fail=$((fail + 1)); echo "FAIL - $1"; [ -n "${2:-}" ] && echo "       $2"; }
check() { if eval "$2"; then ok "$1"; else nok "$1" "$2"; fi; }

sandboxes=()
trap 'rm -rf "${sandboxes[@]}"' EXIT

# Fresh sandbox: a bare origin with a `main` branch, and a main clone of it.
setup() {
  sandbox="$(cd "$(mktemp -d)" && pwd -P)"
  sandboxes+=("$sandbox")
  git init -q --bare -b main "$sandbox/origin.git"
  git clone -q "$sandbox/origin.git" "$sandbox/seed" 2>/dev/null
  git -C "$sandbox/seed" -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m init
  git -C "$sandbox/seed" push -q origin main
  git clone -q "$sandbox/origin.git" "$sandbox/main"
  main="$sandbox/main"

  mkdir -p "$sandbox/bin"
  log="$sandbox/herdr.log"
  cat > "$sandbox/bin/herdr" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$log"
# Emulate \`worktree create\`: branch off --base at --path, tracking the base like Herdr does.
if [ "\$1 \$2" = "worktree create" ]; then
  while [ \$# -gt 0 ]; do
    case "\$1" in --cwd) c=\$2;; --branch) b=\$2;; --base) r=\$2;; --path) p=\$2;; esac; shift
  done
  git -C "\$c" worktree add -q --track -b "\$b" "\$p" "\$r" 2>/dev/null
fi
echo '{"result":{"stub":true}}'
EOF
  chmod +x "$sandbox/bin/herdr"
}

run() { (cd "$1" && shift && PATH="$sandbox/bin:$PATH" HERDR_ENV=1 "$script" "$@") >"$sandbox/out" 2>&1; rc=$?; }

# 1. New branch: herdr creates it from origin/<base> at the standard path.
setup
run "$main" int3-1-new-thing INT3-1
check "new branch exits 0" '[ "$rc" -eq 0 ]'
check "new branch calls worktree create" 'grep -q "^worktree create" "$log"'
check "new branch uses origin/HEAD as base" 'grep -q -- "--base origin/main" "$log"'
check "new branch path under .worktrees" 'grep -q -- "--path $main/.worktrees/int3-1-new-thing" "$log"'
check "new branch passes label and no-focus" 'grep -q -- "--label INT3-1 --no-focus" "$log"'
check "new branch has no upstream" '! git -C "$main" rev-parse --abbrev-ref int3-1-new-thing@{upstream} >/dev/null 2>&1'
check ".worktrees/ added to info/exclude" 'grep -qxF ".worktrees/" "$main/.git/info/exclude"'

# 2. Second run does not duplicate the exclude line.
run "$main" int3-1-new-thing INT3-1
check "exclude line written once" '[ "$(grep -cxF ".worktrees/" "$main/.git/info/exclude")" -eq 1 ]'

# 3. Called from inside a linked worktree: still roots in the main clone.
setup
git -C "$main" worktree add -q "$sandbox/other" -b other 2>/dev/null
run "$sandbox/other" fix/from-linked from-linked
check "linked worktree resolves main clone" 'grep -q -- "--cwd $main --branch fix/from-linked" "$log"'

# 4. Local branch with no worktree: checked out at the standard path, then opened.
setup
git -C "$main" branch fix/local-only
run "$main" fix/local-only local-only
check "local branch gets a worktree" '[ -d "$main/.worktrees/fix/local-only" ]'
check "local branch is opened, not created" 'grep -q "^worktree open .*--path $main/.worktrees/fix/local-only" "$log" && ! grep -q "^worktree create" "$log"'

# 5. Local branch that already has a worktree: reopens that path.
setup
git -C "$main" worktree add -q "$sandbox/elsewhere" -b chore/has-wt 2>/dev/null
run "$main" chore/has-wt has-wt
check "existing worktree is reopened in place" 'grep -q "^worktree open .*--path $sandbox/elsewhere" "$log"'

# 6. Branch only on the remote: tracked locally, then opened.
setup
git -C "$sandbox/seed" push -q origin main:refs/heads/feat/remote-only
run "$main" feat/remote-only remote-only
check "remote branch is tracked" '[ "$(git -C "$main" rev-parse --abbrev-ref feat/remote-only@{upstream} 2>/dev/null)" = origin/feat/remote-only ]'
check "remote branch is opened" 'grep -q "^worktree open .*--path $main/.worktrees/feat/remote-only" "$log"'

# 7. Outside Herdr: refuses before touching anything.
setup
(cd "$main" && PATH="$sandbox/bin:$PATH" HERDR_ENV= "$script" fix/x x) >"$sandbox/out" 2>&1; rc=$?
check "outside Herdr exits non-zero" '[ "$rc" -ne 0 ]'
check "outside Herdr never calls herdr" '[ ! -e "$log" ]'

# 8. Invalid branch name: refuses.
setup
run "$main" "bad..name" bad
check "invalid branch exits non-zero" '[ "$rc" -ne 0 ]'
check "invalid branch never calls herdr" '[ ! -e "$log" ]'

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
