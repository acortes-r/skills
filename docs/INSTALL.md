# Install

## Contents
- Any host, via the CLI
- Manual install per host
- Optional Claude Code overrides
- Verifying an install

## Any host, via the CLI

```bash
npx skills add <your-github-user>/skills --skill review-changes
```

Install every skill in the repository by omitting `--skill`.

## Manual install per host

Copy the skill directory to the host's skills path.

| Host | Path |
|---|---|
| Claude Code — personal | `~/.claude/skills/<name>/` |
| Claude Code — project | `<repo>/.claude/skills/<name>/` |
| Cursor | `~/.cursor/skills/<name>/` |
| Codex, Copilot CLI, Gemini CLI | `~/.agents/skills/<name>/` (cross-runtime alias) |
| Gemini CLI — native | `~/.gemini/skills/<name>/` |

```bash
cp -R skills/review-changes ~/.claude/skills/review-changes
```

The directory name becomes the command the user types, so keep it.

## Optional Claude Code overrides

`SKILL.md` stays within the six spec fields for portability, which leaves out
some Claude Code features. Add them to a personal copy when you want them:

```yaml
context: fork          # run the review in an isolated subagent context
background: false      # return the result in the invoking turn
agent: general-purpose # not Explore — Explore skips CLAUDE.md
effort: high
disallowed-tools: Edit, Write, NotebookEdit
```

`context: fork` keeps the review out of the main conversation. The fork does not
see conversation history, which is fine here because the target is always
resolved from git rather than from what was discussed.

A narrower tool allowlist, so reads stop prompting while the one write does not:

```yaml
allowed-tools: Read, Grep, Glob, Bash(git *), Bash(gh pr view *), Bash(gh pr diff *), Bash(gh api graphql *)
```

Leave `gh api repos/.../reviews` out of the allowlist on purpose. The permission
prompt then acts as the confirmation gate before anything reaches a pull request.

Do not add these fields to the repository copy: `claude.ai` uploads, the Skills
API, and `package_skill.py` reject unknown keys with
`Unexpected key(s) in SKILL.md frontmatter`.

## Verifying an install

```bash
# frontmatter parses and stays within the spec fields
python3 -c "
import sys,pathlib
t=pathlib.Path('skills/review-changes/SKILL.md').read_text().split('---')[1]
keys={l.split(':')[0] for l in t.splitlines() if l and not l.startswith((' ','#'))}
allowed={'name','description','license','compatibility','allowed-tools','metadata'}
extra=keys-allowed
print('extra keys:', extra or 'none')
sys.exit(1 if extra else 0)"

# evals parse
python3 -c "import json;print(len(json.load(open('skills/review-changes/evals/evals.json'))['evals']),'evals')"

# publisher compiles
python3 -m py_compile skills/review-changes/scripts/post_review.py && echo "publisher OK"
```
