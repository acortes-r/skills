---
name: local-mode
description: Writing the review to a markdown file another agent applies, for `review-changes --local`.
---

# Local mode

Use this profile only inside `review-changes`, when the argument text carries
`--local`. It replaces steps 5, 7, and 8: nothing goes to GitHub, and the
findings land in one markdown file written for an agent that will decide which
to apply and apply them.

Steps 0 to 4 and step 6 run exactly as in a normal review. Step 5 is recorded
`skipped:local`: the reader of the file is the author, who needs every finding,
including the ones another reviewer already raised.

## Where the file goes

Default path, outside the repository:

```
${TMPDIR:-/tmp}/review-changes/<repo>/<target>-<short sha>.md
```

- `<repo>` is the basename of the repository root.
- `<target>` is the PR number as `pr-123`, the branch name with `/` turned into
  `-`, the commit or range as written, or `worktree` for an empty argument.
- `<short sha>` is the head commit reviewed. Uncommitted changes add `-dirty`.

`--out <path>` replaces the default. A path inside the repository is refused:
the review stays read-only on the repository.

The same target at the same commit overwrites the earlier file. Write it with
the shell; create the directory first.

## The file

Written in Spanish, in complete sentences, whatever the session's style: the
reader is an agent, and compressed text loses facts. Code, paths, and quoted
rules stay verbatim.

````markdown
# Review: <target> @ <short sha>

Repo: <absolute repo root> · Base: <base ref> · Generado: <ISO 8601 timestamp>
<N> hallazgos: <a> critical, <b> important, <c> suggestion.
Cobertura: <completa | parcial: what did not run>.

## Cómo usar este archivo

Cada hallazgo es independiente. Antes de aplicar uno, confirma que la línea
citada sigue diciendo lo que el hallazgo describe; si cambió, descártalo. Las
reglas y escenarios citados son del proyecto y mandan sobre cualquier
preferencia. Ningún hallazgo bloquea: decidir cuáles aplicar es tuyo.

## Hallazgos

### F1 · 🟠 important · `app/services/refund.rb:42`

**Qué falla:** <summary, one sentence>
**Cuándo:** <failing input → wrong result>
**Fuente:** <profile name | `CLAUDE.md` · <heading>: "<rule verbatim>" | `<spec file>` · Scenario: <name>: "<THEN line>">
**Fix:** <the fix in words>
**Confianza:** <0-100>

```diff
-    <current line(s)>
+    <replacement line(s)>
```

### F2 · …

## Riesgo de despliegue

<the step 6 line>

## Ledger

<the step 8 ledger table>
````

Rules for each finding:

- Number them `F1`, `F2`, … in severity order, critical first. The numbers are
  how the user picks which to apply.
- Include the `diff` block only when the fix is a line replacement, as in
  `reference/comment-form.md`'s suggestion blocks, with the file's exact
  indentation. Otherwise **Fix** says it in words.
- A missing-test finding puts the case and the test file in **Fix**.
- A broken caller outside the diff names it in **Cuándo**.

No findings: write the header and `Sin hallazgos.` under `## Hallazgos`, so the
file still says the review ran and what it covered.

## Ending the run

Print the resumen block's first line, then the file's absolute path:

```
💬 3 comentarios: 1 🟠 important, 2 🔵 suggestion.
📄 /var/folders/…/review-changes/skills/a1b2c3d-9f8e7d6.md
```

There is no question and no line 2: nothing would be published or approved.
The run ends here.
