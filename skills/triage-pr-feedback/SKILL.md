---
name: triage-pr-feedback
description: Use when asked to review, analyze, or triage the comments, threads, or review feedback already left on a pull request — from humans or bots like CodeRabbit and Copilot — and say which apply and which don't. Judges every item against the code and presents a table of verdicts with reasons; changes no code and posts nothing until the user decides.
license: MIT
compatibility: Requires git and an authenticated GitHub CLI (gh). Uses the compound-engineering plugin's ce-resolve-pr-feedback fetch script when it is installed, and plain gh calls otherwise.
allowed-tools: Read, Grep, Glob, Bash
metadata:
  version: 0.1.0
  output: one table of verdicts in the user's language, then a question
  writes: none; fixes, commits, replies and thread resolution wait for the user's decision
---

# Triage PR feedback

Read every open piece of feedback on a pull request, judge each one against the code, and hand the user a **verdict table**. The table is the deliverable: the run ends there, with a question about what to apply. Fixing, committing, replying and resolving threads happen afterwards, only on the user's word, under their usual rules (preview before posting, confirm before committing).

Write the table and every question in the language the user writes in.

## Steps

### 1. Fetch the feedback

Resolve the PR: the number or URL the user gave, else `gh pr view --json number,url,headRefOid`. Then fetch, in this order of preference:

- `get-pr-comments <PR> <OWNER/REPO>` from the compound-engineering plugin, when installed (`ls ~/.claude/plugins/cache/*/compound-engineering/*/skills/ce-resolve-pr-feedback/scripts/get-pr-comments`). It returns unresolved threads, top-level comments and review bodies, paginated.
- Otherwise `gh api graphql` for `reviewThreads` (with `isResolved`, `isOutdated`, `path`, `line`, comments) and `gh api repos/<o>/<r>/pulls/<n>/reviews` plus `.../issues/<n>/comments`.

Also read what arrived since the last push: review bodies carry bot comments that fall **outside the diff** (CodeRabbit lists them under "Outside diff range comments"), and a reviewer's re-review summary may live in a top-level comment while its threads are already resolved.

Drop silently: bot boilerplate (walkthroughs, "Fix comments" checkboxes, risk badges), approvals with no ask, and replies the PR author already posted. Done when every remaining item is an open request: something to fix, answer, or decide.

### 2. Judge each item

Read [reference/rubric.md](reference/rubric.md) now and apply it to the whole batch at once. Read the code at every location an item names; a verdict taken from the comment text alone is a guess. Done when every item has a verdict and a reason backed by a file, a line, a test, or a contract you actually read.

### 3. Present the table

One row per item, numbered so the user can answer by number, with the headers translated to the user's language:

| # | Author | Level | Where | Comment | Applies? | Why |
|---|---|---|---|---|---|---|

- **Level**: the reviewer's own severity (Medium, Minor, nit…), or `—`.
- **Where**: `file:line` as it reads at the PR head.
- **Comment**: the ask in one line, in your own words.
- **Applies?**: ✅ yes · ⚠️ partly · ❌ no · 🔎 your call.
- **Why**: the evidence in one or two lines, with the file and line that settles it.

Group items that share one fix and say so in the row. Under the table, give the counts, which items one fix would close together, and your recommendation for each 🔎 row. Close with one question: which items to apply, and whether the ⚠️ and 🔎 rows go in now or as follow-ups.

Done when the table is shown and the question asked. The run stops here.

## After the user decides

The user's answer opens a new task under their own rules. Apply the items they chose, one atomic commit per fix group, then draft the thread replies (with the commit SHA once it is pushed) and show them before posting. Resolve only the threads the user agrees to resolve; items declined with evidence usually stay open for the reviewer to close.
