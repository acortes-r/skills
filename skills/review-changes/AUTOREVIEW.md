# Autoreview workflow

An optional self-review the coding agent offers at two moments: after it creates
a local commit, and before it creates a pull request. The review runs
`review-changes --local` in a separate agent, and the coding agent triages the
report with the user before applying anything.

This file has two parts. **The workflow** is what the agent does at each
moment. **Installing it** is what to do when the user says "implement the
workflow in this file".

## The workflow

### When it triggers

| Moment | Target |
|---|---|
| right after you create a local commit | that commit: `<short sha>` |
| when the user asks to push and open a PR, before creating it | the whole branch: `origin/<base>...HEAD`, where `<base>` is the PR's base branch |

The commit that applies review findings is a local commit too, so the question
comes again after it. That is intended: each round is optional.

### Steps

1. **Ask.** One question, nothing else in the message:
   `¿Corro el review de <short sha>?` or `¿Corro el review de la rama antes de crear el PR?`
   On anything other than a yes, continue without it.
2. **Run it in a fresh agent.** Dispatch a subagent that invokes
   `/review-changes --local <target>`. The agent that wrote the code does not
   review it. No subagent tool: run it inline and say so in one line.
3. **Read the report.** The run ends with a `📄 <path>` line. Read that file.
   Its findings are numbered `F1`, `F2`, … and each one carries its location,
   failing case, source, fix, and confidence.
4. **Triage.** For every finding, say whether it applies, with a one-line
   reason. Before judging one, check that the cited line still says what the
   finding describes; if it moved or changed, the finding does not apply. A
   quoted project rule or OpenSpec scenario outranks your preference.

   ```
   F1 🟠 aplica — el monto en Float rompe la regla de CLAUDE.md.
   F2 🔵 no aplica — la línea ya cambió en el commit siguiente.
   F3 🔵 aplica — el caso de reembolso 0 no tiene test.
   ```

5. **Ask which to apply.** One question:
   `¿Aplico todos (F1–F3) o solo los que recomiendo (F1, F3)?`
   The user may also name a list. No findings: say so and continue.
6. **Apply.** Apply exactly the findings chosen. Run the tests that cover the
   files you touched. Then commit by the user's usual commit rules, which brings
   back step 1.
7. **Before a PR, go on to the PR.** Once the branch round is settled, continue
   with the PR as the user asked, including any preview they require.

### Boundaries

- This workflow never publishes anything to GitHub. `--local` sends nothing.
- A finding is applied only after the user's answer in step 5.
- A declined review is not offered again for the same commit.

## Installing it

When the user asks you to implement this workflow:

1. **Check the skill.** `review-changes` must be installed at version 0.7.0 or
   later: its `SKILL.md` frontmatter has `version:`, and its body mentions
   `--local`. Older or missing: tell the user and stop.
2. **Pick the instruction file** your harness loads on every session:
   `~/.claude/CLAUDE.md` for Claude Code, `~/.codex/AGENTS.md` for Codex. Any
   other harness, or a project-only install: ask the user which file.
3. **Look for an existing install.** Search that file for `Autoreview`. Found:
   replace those lines with the block below instead of adding a second copy.
4. **Show, then write.** Print the block, the file, and where it goes (the
   section the user keeps their working rules in, otherwise the end). Write it
   only after the user's OK.

The block, with `<path>` replaced by this file's absolute path:

```markdown
- Autoreview, siempre opcional: después de cada commit local que crees, pregúntame si corro el review de ese commit; antes de crear un PR, pregúntame lo mismo para toda la rama. Si digo que no, sigue sin él.
- Si digo que sí: sigue el flujo de `<path>`: review con `/review-changes --local` en un subagente, triage de cada `F#` (aplica o no, con razón de una línea), y pregúntame si aplico todos o solo los que recomiendas.
```
