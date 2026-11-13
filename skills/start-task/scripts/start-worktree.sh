#!/usr/bin/env bash
# Create (or reopen) a Herdr worktree workspace for a branch, rooted in the main clone.
# Works in Herdr TUI (a workspace) and in the Herdr app (a space); see backend.sh.
# Usage:
#   start-worktree.sh --bases                   print base candidates, the default first
#   start-worktree.sh <branch> <label> [base]   create or reopen; base defaults to origin/HEAD
# Prints JSON on success; .result.workspace.workspace_id is the workspace (TUI) or space (app).
set -euo pipefail
# shellcheck source=backend.sh
. "$(dirname "$0")/backend.sh"

usage="usage: start-worktree.sh --bases | start-worktree.sh <branch> <label> [base]"

# Main clone, even when called from inside a linked worktree or a subdirectory.
# A relative --git-common-dir is relative to the cwd; resolve it with cd instead of
# --path-format=absolute, which Git < 2.31 echoes back instead of rejecting.
common_dir="$(cd "$(git rev-parse --git-common-dir)" && pwd -P)"
main="$(dirname "$common_dir")"

default_base() {
  local ref
  ref="$(git -C "$main" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)" \
    || { echo "error: origin/HEAD not set; run: git -C $main remote set-head origin --auto" >&2; exit 1; }
  echo "${ref#origin/}"
}

if [ "${1:-}" = "--bases" ]; then
  git -C "$main" fetch --quiet --prune origin
  default="$(default_base)"
  echo "$default"
  # Long-lived branches that commonly serve as a base, when the remote has them.
  for b in main master develop development staging release; do
    [ "$b" = "$default" ] && continue
    git -C "$main" show-ref --verify --quiet "refs/remotes/origin/$b" && echo "$b"
  done
  exit 0
fi

branch="${1:?$usage}"
label="${2:?$usage}"
base="${3:-}"

backend="$(herdr_backend)" || exit 1
git check-ref-format --branch "$branch" >/dev/null || { echo "error: invalid branch name: $branch" >&2; exit 1; }
if [ -n "$base" ]; then
  git check-ref-format --branch "$base" >/dev/null || { echo "error: invalid base name: $base" >&2; exit 1; }
else
  base="$(default_base)"
fi

git -C "$main" fetch --quiet origin "$base" "$branch" 2>/dev/null \
  || git -C "$main" fetch --quiet origin "$base" 2>/dev/null \
  || true

# Prefer the remote base; fall back to a local-only branch, e.g. stacking on unpushed work.
if git -C "$main" show-ref --verify --quiet "refs/remotes/origin/$base"; then
  base_ref="origin/$base"
elif git -C "$main" show-ref --verify --quiet "refs/heads/$base"; then
  base_ref="$base"
else
  echo "error: base branch not found on origin or locally: $base" >&2
  exit 1
fi

# Keep .worktrees/ and each worktree's task brief out of `git status`
# without touching the tracked .gitignore.
exclude="$common_dir/info/exclude"
for pattern in '.worktrees/' '/.task-brief.md'; do
  grep -qxF "$pattern" "$exclude" 2>/dev/null || echo "$pattern" >> "$exclude"
done

path="$main/.worktrees/$branch"

# Herdr TUI opens worktrees itself. The Herdr app has no worktree command: git makes
# the worktree, then the app shows it as a space.
open_worktree() {  # <path>
  if [ "$backend" = tui ]; then
    herdr worktree open --cwd "$main" --path "$1" --label "$label" --no-focus
  else
    open_space "$1"
  fi
}

# Reuse the space already showing this folder, else make one named after the label.
# space.new shows the new space, so the view goes back to the caller's space after.
open_space() {  # <path>
  local space here
  space="$(herdr-app ls | python3 -c '
import json, sys
for s in json.load(sys.stdin)["spaces"]:
    if s.get("folder") == sys.argv[1]:
        print(s["id"]); break
' "$1")"
  if [ -z "$space" ]; then
    here="$(hc get "$HC_TERMINAL_ID" | python3 -c 'import json, sys; print(json.load(sys.stdin)["labels"].get("herdr.space", ""))')"
    space="$(herdr-app do space.new --name "$label" --folder "$1" | python3 -c 'import json, sys; print(json.load(sys.stdin)["space"])')"
    [ -z "$here" ] || herdr-app do space.select --id "$here" >/dev/null
  fi
  python3 -c 'import json, sys; print(json.dumps({"backend": "app", "result": {"workspace": {"workspace_id": sys.argv[1], "path": sys.argv[2]}}}))' "$space" "$1"
}

if git -C "$main" show-ref --verify --quiet "refs/heads/$branch"; then
  # Branch exists locally: reuse its worktree if it has one, else check it out at the standard path.
  existing="$(git -C "$main" worktree list --porcelain | awk -v b="branch refs/heads/$branch" '/^worktree /{p=substr($0,10)} $0==b{print p}')"
  if [ -n "$existing" ]; then
    open_worktree "$existing"
  else
    git -C "$main" worktree add "$path" "$branch" >&2
    open_worktree "$path"
  fi
elif git -C "$main" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
  # Branch only on the remote: track it.
  git -C "$main" worktree add --track -b "$branch" "$path" "origin/$branch" >&2
  open_worktree "$path"
elif [ "$backend" = tui ]; then
  herdr worktree create --cwd "$main" --branch "$branch" --base "$base_ref" \
    --path "$path" --label "$label" --no-focus
  # The new branch may inherit the base as upstream; drop it so the first
  # `git push -u origin <branch>` sets the right one and `git pull` never pulls the base.
  git -C "$main" branch --unset-upstream "$branch" 2>/dev/null || true
else
  # --no-track for the same reason: the base is never the branch's upstream.
  git -C "$main" worktree add --no-track -b "$branch" "$path" "$base_ref" >&2
  open_space "$path"
fi
