#!/usr/bin/env python3
"""Publish review findings as ONE non-blocking GitHub review.

Invariants enforced here rather than left to the caller:

  * The review event is always COMMENT. APPROVE and REQUEST_CHANGES cannot be
    produced by this script at all.
  * Every inline target is validated against the diff before posting, so a
    finding anchored outside a hunk degrades into the review body instead of
    failing the whole review with a 422.
  * A finding whose path and opening text were already posted is skipped, so
    retrying after a partial failure does not duplicate comments, and a
    re-review does not repost a comment whose code has since moved lines.

Usage:
    post_review.py --repo owner/name --pr 123 \
        [--findings findings.json] [--replies replies.json] [--dry-run]

findings.json is a JSON array:
    [{"path": "app/x.rb", "line": 42, "side": "RIGHT", "body": "..."}]
`side` defaults to RIGHT. Omit `line` for a finding with no single-line anchor.

replies.json answers questions the author asked on our own earlier threads:
    [{"in_reply_to": 123456789, "body": "..."}]
`in_reply_to` is the id of the comment being answered. A reply whose text is
already on that thread is skipped.

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


def existing_comments(repo, pr):
    """Inline comments already on the PR, or None when they cannot be read."""
    try:
        raw = gh(["api", f"repos/{repo}/pulls/{pr}/comments", "--paginate"])
    except RuntimeError as err:
        # Not fatal: without this the run may repost a comment, which is better
        # than refusing to publish at all. Say so plainly.
        print(f"post_review: could not read existing comments ({err}). "
              "Idempotency check skipped.", file=sys.stderr)
        return None
    return json.loads(raw or "[]")


def first_line(body):
    lines = (body or "").splitlines()
    return lines[0] if lines else ""


def posted_signatures(comments):
    """{(path, first_body_line)} for findings this PR already carries.

    The line number is deliberately not part of the key. Between two runs of a
    review the code moves, so the same finding comes back anchored somewhere
    else; keying on the line would let it be posted a second time.
    """
    return {(item.get("path"), first_line(item.get("body")))
            for item in comments}


def replied_signatures(comments):
    """{(thread_root_id, first_body_line)} for replies already on a thread.

    GitHub reports every reply with `in_reply_to_id` set to the thread's first
    comment, which is the same id a caller passes as `in_reply_to`.
    """
    return {(item.get("in_reply_to_id"), first_line(item.get("body")))
            for item in comments if item.get("in_reply_to_id")}


def load_array(path, label):
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        fail(f"{label} file not found: {path}")
    except json.JSONDecodeError as err:
        fail(f"{label} file is not valid JSON: {err}")
    if not isinstance(data, list):
        fail(f"{label} file must contain a JSON array")
    return data


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--findings", help="JSON array file")
    parser.add_argument("--replies", help="JSON array file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.findings and not args.replies:
        fail("nothing to do: pass --findings, --replies, or both")

    findings = load_array(args.findings, "findings")
    replies = load_array(args.replies, "replies")

    if not findings and not replies:
        print("post_review: no findings and no replies. "
              "Nothing published, no review created.")
        return

    try:
        gh(["auth", "status"])
    except RuntimeError:
        fail("gh is not authenticated. Run: gh auth login")

    targets = set()
    if findings:
        try:
            patch = gh(["pr", "diff", str(args.pr), "--repo", args.repo])
        except RuntimeError as err:
            fail(f"could not read the diff for PR #{args.pr} in {args.repo}: {err}")
        targets = commentable_lines(patch)

    comments = existing_comments(args.repo, args.pr)
    posted = posted_signatures(comments) if comments is not None else set()
    replied = replied_signatures(comments) if comments is not None else set()

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

        if (path, first_line(body)) in posted:
            skipped += 1
            continue

        if line is not None and (path, int(line)) in targets:
            inline.append({"path": path, "line": int(line),
                           "side": side, "body": body})
        else:
            anchor = f"`{path}:{line}`" if line is not None else f"`{path}`"
            degraded.append(f"- {anchor} — {' '.join(body.split())}")

    pending_replies = []
    for reply in replies:
        target = reply.get("in_reply_to")
        body = (reply.get("body") or "").strip()
        if not target or not body:
            print("post_review: skipping a reply with no in_reply_to or no body",
                  file=sys.stderr)
            continue
        if (target, first_line(body)) in replied:
            skipped += 1
            continue
        pending_replies.append({"in_reply_to": target, "body": body})

    if not inline and not degraded and not pending_replies:
        print(f"post_review: everything was already posted ({skipped}). "
              "No review created.")
        return

    payload = None
    if inline or degraded:
        total = len(inline) + len(degraded)
        body = f"{total} comentarios. Ninguno bloquea el merge."
        if degraded:
            body += "\n\nFuera de las líneas del diff:\n" + "\n".join(degraded)
        payload = {"event": REVIEW_EVENT, "body": body, "comments": inline}

    counters = (f"inline={len(inline)} degraded={len(degraded)} "
                f"replies={len(pending_replies)} already-posted={skipped}")

    if args.dry_run:
        if payload is not None:
            print("post_review: dry run. Payload that would be sent:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("post_review: dry run. No review would be created.")
        if pending_replies:
            print("post_review: replies that would be sent:")
            print(json.dumps(pending_replies, indent=2, ensure_ascii=False))
        print(f"post_review: {counters}")
        return

    url = ""
    if payload is not None:
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

    failed = 0
    for reply in pending_replies:
        endpoint = (f"repos/{args.repo}/pulls/{args.pr}/comments/"
                    f"{reply['in_reply_to']}/replies")
        try:
            gh(["api", endpoint, "--input", "-"],
               stdin=json.dumps({"body": reply["body"]}))
        except RuntimeError as err:
            failed += 1
            print(f"post_review: reply to comment {reply['in_reply_to']} "
                  f"was rejected.\n{err}", file=sys.stderr)

    print(f"post_review: published as {REVIEW_EVENT} — {counters}")
    if url:
        print(f"post_review: {url}")
    if failed:
        print(f"post_review: {failed} reply(ies) failed. The review itself "
              "was published.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
