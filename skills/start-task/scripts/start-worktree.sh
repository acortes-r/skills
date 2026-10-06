#!/usr/bin/env bash
# Create (or reopen) a Herdr worktree workspace for a branch, rooted in the main clone.
# Usage: start-worktree.sh <branch> <label>
# Prints the Herdr JSON response on success.
set -euo pipefail

branch="${1:?usage: start-worktree.sh <branch> <label>}"
label="${2:?usage: start-worktree.sh <branch> <label>}"

[ "${HERDR_ENV:-}" = 1 ] || { echo "error: not running inside a Herdr pane" >&2; exit 1; }
git check-ref-format --branch "$branch" >/dev/null || { echo "error: invalid branch name: $branch" >&2; exit 1; }

# Main clone, even when called from inside a linked worktree.
common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
main="$(dirname "$common_dir")"

base_ref="$(git -C "$main" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)" \
  || { echo "error: origin/HEAD not set; run: git -C $main remote set-head origin --auto" >&2; exit 1; }
base="${base_ref#origin/}"

git -C "$main" fetch --quiet origin "$base" "$branch" 2>/dev/null || git -C "$main" fetch --quiet origin "$base"

# Keep .worktrees/ out of `git status` without touching the tracked .gitignore.
exclude="$common_dir/info/exclude"
grep -qxF '.worktrees/' "$exclude" 2>/dev/null || echo '.worktrees/' >> "$exclude"

path="$main/.worktrees/$branch"

if git -C "$main" show-ref --verify --quiet "refs/heads/$branch"; then
  # Branch exists locally: reuse its worktree if it has one, else check it out at the standard path.
  existing="$(git -C "$main" worktree list --porcelain | awk -v b="branch refs/heads/$branch" '/^worktree /{p=substr($0,10)} $0==b{print p}')"
  if [ -n "$existing" ]; then
    herdr worktree open --cwd "$main" --path "$existing" --label "$label" --no-focus
  else
    git -C "$main" worktree add "$path" "$branch" >&2
    herdr worktree open --cwd "$main" --path "$path" --label "$label" --no-focus
  fi
elif git -C "$main" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
  # Branch only on the remote: track it.
  git -C "$main" worktree add --track -b "$branch" "$path" "origin/$branch" >&2
  herdr worktree open --cwd "$main" --path "$path" --label "$label" --no-focus
else
  herdr worktree create --cwd "$main" --branch "$branch" --base "origin/$base" \
    --path "$path" --label "$label" --no-focus
  # The new branch inherits origin/<base> as upstream; drop it so the first
  # `git push -u origin <branch>` sets the right one and `git pull` never pulls the base.
  git -C "$main" branch --unset-upstream "$branch" 2>/dev/null || true
fi
