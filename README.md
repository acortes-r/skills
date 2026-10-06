# Personal skills

Agent skills that install into any host implementing the
[Agent Skills](https://agentskills.io) standard — Claude Code, Cursor, Codex,
Gemini CLI, OpenCode, and others.

## Install one skill

```bash
npx skills add <your-github-user>/skills --skill review-changes
```

Replace `<your-github-user>` with the account this repository lives under.

## Update an installed skill

```bash
npx skills update review-changes --global
```

Naming the skill matters: `npx skills update` with no arguments updates every
skill you have installed. `--global` targets user-level installs, `--project`
a skill installed into a repository.

The CLI records where each skill came from in `~/.agents/.skill-lock.json`, so
it pulls from the right source without being told. Check what you ended up with:

```bash
grep -m1 "version:" ~/.agents/skills/review-changes/SKILL.md
```

An agent session keeps the skills it loaded at startup. Start a new session for
the update to take effect.

## Skills

| Skill | What it does |
|---|---|
| [review-changes](skills/review-changes/) | Non-blocking code review: loads the project's own rules, verifies findings adversarially, dedupes against its own earlier comments and other reviewers, publishes GitHub suggestions, approves only after asking, never on its own |
| [start-task](skills/start-task/) | Opens a git worktree and branch for a new task as a Herdr workspace, named from the Linear issue or the task description; proposes the name and waits before creating anything |

## Layout

```
skills/<name>/
├── SKILL.md          # required: spec frontmatter plus instructions
├── README.md         # install and behavior
├── reference/        # profiles loaded on demand
├── scripts/          # deterministic helpers, executed not read
├── tests/            # tests for the scripts, no network
├── evals/evals.json  # scenarios the skill must satisfy
└── agents/*.yaml     # per-host adapters
```

Every `SKILL.md` restricts its frontmatter to the six spec fields — `name`,
`description`, `license`, `compatibility`, `allowed-tools`, `metadata` — so the
same file loads in Claude Code, in `claude.ai` uploads, through the Skills API,
and in other hosts without an unexpected-key error. Host-specific configuration
lives in `agents/` and in [docs/INSTALL.md](docs/INSTALL.md), never in
`SKILL.md`.

See [docs/INSTALL.md](docs/INSTALL.md) for per-host paths and optional overrides.
