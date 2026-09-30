# Personal skills

Agent skills that install into any host implementing the
[Agent Skills](https://agentskills.io) standard — Claude Code, Cursor, Codex,
Gemini CLI, OpenCode, and others.

## Install one skill

```bash
npx skills add <your-github-user>/skills --skill review-changes
```

Replace `<your-github-user>` with the account this repository lives under.

## Skills

| Skill | What it does |
|---|---|
| [review-changes](skills/review-changes/) | Non-blocking code review: loads the project's own rules, verifies findings adversarially, dedupes against its own earlier comments and other reviewers, publishes GitHub suggestions, approves only diffs that change no behavior |

## Layout

```
skills/<name>/
├── SKILL.md          # required: spec frontmatter plus instructions
├── README.md         # install and behavior
├── reference/        # profiles loaded on demand
├── scripts/          # deterministic helpers, executed not read
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
