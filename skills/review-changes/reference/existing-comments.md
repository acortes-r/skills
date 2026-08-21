---
name: existing-comments
description: Dedupe pass against reviewers already on the PR, for `review-changes`.
---

# Existing comments

Use this profile only inside `review-changes`, after verification and before
publishing. Its purpose is to not repeat what a human or another bot already
said on this pull request.

## Contents
- Collect
- Drop
- Keep
- Reply instead of duplicate
- Ledger

## Collect

```bash
# Inline threads with resolution state — preferred source
gh api graphql -f query='
  query($owner:String!,$repo:String!,$num:Int!){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$num){
        reviewThreads(first:100){ nodes{
          id isResolved isOutdated path line
          comments(first:20){ nodes{ author{login} body createdAt } } } } } } }' \
  -F owner=<owner> -F repo=<repo> -F num=<n>

# Fallback when GraphQL is unavailable: no resolution state
gh api repos/<owner>/<repo>/pulls/<n>/comments --paginate \
  --jq '.[] | {path, line, user: .user.login, body}'

# PR-level comments — bot summaries live here
gh api repos/<owner>/<repo>/issues/<n>/comments --paginate \
  --jq '.[] | {user: .user.login, body}'

# Review bodies and states
gh pr view <n> --json reviews
```

Used the REST fallback: resolution state is unknown. Treat every thread as
unresolved and say so in the ledger.

Classify each author as human or bot. Known review bots: `coderabbitai`,
`codacy-production`, `sonarcloud`, `sonarqubecloud`, `codecov`, `sourcery-ai`,
`deepsource-autofix`, `github-actions`, `copilot-pull-request-reviewer`,
`greptile-apps`, `ellipsis-dev`. Any login ending in `[bot]` is a bot.

Bot summaries at PR level often carry findings that never became inline
threads. Read their bodies, not just the thread list.

## Drop

Drop a survivor when it is already covered:

- Same `path`, line within ±3, and the same underlying problem — regardless of
  author, and regardless of wording.
- A **resolved** thread covers it. Someone already decided. Do not reopen.
- An **outdated** thread covers it and the current diff no longer contains the
  problem.
- A bot's PR-level summary names it, even with no inline thread.
- Your own comment from a previous run of this skill covers it.

Matching is semantic, not textual. "N+1 en el loop de reservas" and "this query
runs once per iteration" on the same line are one finding.

## Keep

- Nothing existing covers it.
- An outdated thread covers it **and** the current diff still has the problem.
  Publish fresh and note in one clause that it revisits an earlier comment.
- The existing comment is wrong about the mechanism. Publish yours; do not
  argue with theirs in the body.

## Reply instead of duplicate

Existing comment names the symptom and yours names the root cause: publish as a
reply on that thread, not as a new comment. Carry the thread id through to
publishing.

## Ledger

Report the drop count and its sources, for example
`dedup: 4 omitidos — coderabbit 3, @juan 1`.

The count is for the local report only. Never post it, and never post a
comment about deduplication.
