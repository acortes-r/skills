---
name: docs-only
description: Classifying a diff that changes no behavior, and approving it, for `review-changes`.
---

# Docs-only diffs

Use this profile only inside `review-changes`, in step 2, before any other
profile is routed. It answers one question: **does this diff change behavior?**

When the answer is no, the review can end in `APPROVE` instead of `COMMENT`.
That is the only case where this skill approves anything, and it still needs the
user's explicit go.

## Contents
- The question
- Documentation files
- Files that look like documentation but are not
- Comment-only changes to code files
- When in doubt
- The approve flow
- Ledger

## The question

A diff changes no behavior when **every** changed file is either:

1. a documentation file, or
2. a code file whose every added and removed line is a comment or a docstring.

One file failing both conditions is enough. The diff then goes through the
normal `COMMENT` review and this profile records `skipped:behavior-change`.

Deleting or renaming a documentation file still changes no behavior. Deleting a
code file does.

## Documentation files

- `*.md`, `*.mdx`, `*.rst`, `*.adoc`, `*.txt`
- `openspec/**` — specs, changes, tasks
- `docs/**`, except the paths listed as rule contracts below
- `README*`, `CHANGELOG*`, `LICENSE*`, `NOTICE*`
- images and diagrams referenced only by the above

## Files that look like documentation but are not

These are text, and changing them changes what the project does. A diff
touching any of them is a behavior change:

**Rule contracts** — `reference/project-rules.md` treats these as the project's
law, and this skill already reviews a change to one as a finding:

- `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, at any depth
- `.cursor/rules/*.mdc`, `.cursorrules`, `.github/copilot-instructions.md`
- `CONTRIBUTING.md`
- `docs/adr/**`, `docs/architecture/**`, `docs/decisions/**`

**Executable text** — `.github/workflows/*.yml`, `Dockerfile`, `Makefile`,
`*.sql`, `package.json`, lockfiles, `.env*`, IaC templates, and any other file
a build, deploy, or runtime step reads.

**Markdown a build step consumes** — doctests, literate configuration, a
snippet runner. Rare, but if the repository has one, its markdown is code.

## Comment-only changes to code files

A code file qualifies when every `+` and `-` line in its hunks is a comment or
a docstring in that file's language. Anything else — a moved statement, a
changed string literal, a reordered import, whitespace that the language gives
meaning to — is a behavior change.

Two traps:

- A comment that is a directive is not a comment. `# rubocop:disable`,
  `// @ts-ignore`, `# type: ignore`, `// eslint-disable-next-line`,
  `# noqa`, build tags, and pragmas all change what tooling does.
- A docstring that a framework reads at runtime — an OpenAPI annotation, a
  serializer schema comment, an attribute macro — is behavior.

## When in doubt

Treat the diff as a behavior change and run the normal review. The cost of
being wrong in that direction is an unnecessary comment. The cost of being
wrong in the other direction is an approval nobody looked at.

Never infer the language's comment syntax from a guess. Unknown extension means
unknown syntax means behavior change.

## The approve flow

1. Classify. Not a docs-only diff: stop here, continue the normal review.
2. Skip the code profiles in step 2. `migrations.md`, `frontend.md`,
   `backend.md`, and `security.md` have nothing to say about prose; record them
   as `skipped:docs-only`.
3. Review the prose against the project rules anyway. A docs-only diff can still
   contradict a spec, document an endpoint that does not exist, or leave an
   OpenSpec task claiming something the code never did. Those are notes.
4. Print the resumen block and the review body, and say plainly that sending it
   **approves the pull request**. Nothing is sent yet.
5. Ask for the go. The go has to be for the approval, not just for the text. On
   anything else, keep it local.
6. On a yes, publish with `--approve`. No inline comments are created in this
   mode; every note lives in the body.

No notes at all means no body. The approval goes in bare and the question is
`¿Apruebo el PR sin comentario?`. A docs-only diff with nothing wrong in it
gets an approval and silence, not a comment announcing that there is nothing to
comment.

Already approved by us at this same head commit: do not approve again. The
resumen block says `ya aprobado en <short sha>` and asks nothing.

## Ledger

```
| docs-only | ran | 6 archivos, 0 de comportamiento; aprobado con 3 notas |
| docs-only | skipped | behavior-change: app/models/user.rb |
```
