#!/usr/bin/env python3
"""Publish review findings as ONE non-blocking GitHub review.

Invariants enforced here rather than left to the caller:

  * The review event is always COMMENT. APPROVE and REQUEST_CHANGES cannot be
    produced by this script at all.
  * Every inline target is validated against the diff before posting, so a
    finding anchored outside a hunk degrades into the review body instead of
    failing the whole review with a 422.
  * A finding whose path, line, and opening text were already posted is skipped,
    so retrying after a partial failure does not duplicate comments.

Usage:
    post_review.py --repo owner/name --pr 123 --findings findings.json [--dry-run]

findings.json is a JSON array:
    [{"path": "app/x.rb", "line": 42, "side": "RIGHT", "body": "..."}]
`side` defaults to RIGHT. Omit `line` for a finding with no single-line anchor.

Requires python3 and an authenticated GitHub CLI. Does not require jq.
"""

import argparse
import json
import re
import subprocess
import sys

# Only these two review events are meaningful for this tool, and only one is
# allowed. Approval and blocking are the human's decision, never the script's.
REVIEW_EVENT = "COMMENT"

HUNK = re.compile(r"^@@ .*?\+(\d+)")


def fail(message):
    print(f"post_review: {message}", file=sys.stderr)
    sys.exit(1)


def gh(args, stdin=None):
    """Run gh and return stdout. Raises RuntimeError with gh's own message."""
    try:
        done = subprocess.run(
            ["gh", *args],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        fail("gh is not installed. Install GitHub CLI 2.40 or newer.")
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or f"gh {' '.join(args)} failed")
    return done.stdout


def commentable_lines(patch):
    """Line numbers that can carry an inline comment, as {(path, line)}.

    Any line present in a hunk is addressable on the RIGHT side: added lines and
    context lines both. Deleted lines are not offered as targets.
    """
    targets = set()
    path = None
    line = 0
    for raw in patch.splitlines():
        if raw.startswith("+++ "):
            candidate = raw[6:]
            path = None if candidate in ("dev/null", "") else candidate
            continue
        if raw.startswith("@@"):
            found = HUNK.match(raw)
            line = int(found.group(1)) if found else 0
            continue
        if path is None or line == 0:
            continue
        if raw.startswith("+") or raw.startswith(" "):
            targets.add((path, line))
            line += 1
        # Deletions and metadata lines do not advance the new-file counter.
    return targets


def already_posted(repo, pr):
    """{(path, line, first_body_line)} for comments this PR already carries."""
    try:
        raw = gh(["api", f"repos/{repo}/pulls/{pr}/comments", "--paginate"])
    except RuntimeError as err:
        # Not fatal: without this set the run may repost a comment, which is
        # better than refusing to publish at all. Say so plainly.
        print(f"post_review: could not read existing comments ({err}). "
              "Idempotency check skipped.", file=sys.stderr)
        return set()
    seen = set()
    for item in json.loads(raw or "[]"):
        body = (item.get("body") or "").splitlines()
        first = body[0] if body else ""
        seen.add((item.get("path"), item.get("line") or 0, first))
    return seen


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--findings", required=True, help="JSON array file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        with open(args.findings, encoding="utf-8") as handle:
            findings = json.load(handle)
    except FileNotFoundError:
        fail(f"findings file not found: {args.findings}")
    except json.JSONDecodeError as err:
        fail(f"findings file is not valid JSON: {err}")

    if not isinstance(findings, list):
        fail("findings file must contain a JSON array")
    if not findings:
        print("post_review: no findings. Nothing published, no review created.")
        return

    try:
        gh(["auth", "status"])
    except RuntimeError:
        fail("gh is not authenticated. Run: gh auth login")

    try:
        patch = gh(["pr", "diff", str(args.pr), "--repo", args.repo])
    except RuntimeError as err:
        fail(f"could not read the diff for PR #{args.pr} in {args.repo}: {err}")

    targets = commentable_lines(patch)
    posted = already_posted(args.repo, args.pr)

    inline, degraded, skipped = [], [], 0

    for finding in findings:
        path = finding.get("path")
        body = (finding.get("body") or "").strip()
        line = finding.get("line")
        side = finding.get("side") or "RIGHT"

        if not path or not body:
            print("post_review: skipping a finding with no path or no body",
                  file=sys.stderr)
            continue

        first = body.splitlines()[0]
        if (path, line or 0, first) in posted:
            skipped += 1
            continue

        if line is not None and (path, int(line)) in targets:
            inline.append({"path": path, "line": int(line),
                           "side": side, "body": body})
        else:
            anchor = f"`{path}:{line}`" if line is not None else f"`{path}`"
            degraded.append(f"- {anchor} — {' '.join(body.split())}")

    if not inline and not degraded:
        print(f"post_review: every finding was already posted ({skipped}). "
              "No review created.")
        return

    total = len(inline) + len(degraded)
    body = f"{total} comentarios. Ninguno bloquea el merge."
    if degraded:
        body += "\n\nFuera de las líneas del diff:\n" + "\n".join(degraded)

    payload = {"event": REVIEW_EVENT, "body": body, "comments": inline}

    if args.dry_run:
        print("post_review: dry run. Payload that would be sent:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"post_review: inline={len(inline)} degraded={len(degraded)} "
              f"already-posted={skipped}")
        return

    try:
        response = gh(
            ["api", f"repos/{args.repo}/pulls/{args.pr}/reviews", "--input", "-"],
            stdin=json.dumps(payload),
        )
    except RuntimeError as err:
        print(f"post_review: the API rejected the review. Nothing was published.\n{err}",
              file=sys.stderr)
        print("post_review: payload kept for inspection:", file=sys.stderr)
        print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    url = json.loads(response or "{}").get("html_url", "")
    print(f"post_review: published as {REVIEW_EVENT} — inline={len(inline)} "
          f"degraded={len(degraded)} already-posted={skipped}")
    if url:
        print(f"post_review: {url}")


if __name__ == "__main__":
    main()
