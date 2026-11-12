#!/usr/bin/env python3
"""Publish one round of review findings as ONE GitHub review.

Invariants enforced here rather than left to the caller:

  * The review event is COMMENT, or APPROVE when --approve is passed for a diff
    the caller has already classified as approvable. REQUEST_CHANGES cannot be
    produced by this script at all.
  * --approve carries only 🔵 findings, and no pending threads. A 🔴, a 🟠, or
    a pending thread is refused, so an approval can never go out alongside
    something that contradicts it. With nothing at all to say it carries no
    body either.
  * The same head commit is never approved twice, and never gets two round
    summaries.
  * Every review body opens with its round and the head commit it reviewed,
    `Ronda N (abc1234)`, so the author can tell a re-review ran and on which
    push. N is derived from the reviews already on the PR; no state
    is kept anywhere else.
  * Every inline target is validated against the diff before posting, so a
    finding anchored outside a hunk degrades into the review body instead of
    failing the whole review with a 422.
  * A finding whose path and opening text (what fails and the failing case,
    the prose before any suggestion block) were already posted is skipped, so
    retrying after a partial failure does not duplicate comments, and a
    re-review does not repost a comment whose code has since moved lines.
  * A thread is resolved only when it is still open and this account opened it
    with a severity marker.

Usage:
    post_review.py --repo owner/name --pr 123 \
        [--findings findings.json] [--replies replies.json] \
        [--summary summary.json] [--resolve resolve.json] [--dry-run]
    post_review.py --repo owner/name --pr 123 --approve \
        [--notes notes.json | --findings findings.json] [--replies replies.json] \
        [--summary summary.json] [--resolve resolve.json]

findings.json is a JSON array:
    [{"path": "app/x.rb", "line": 42, "side": "RIGHT", "body": "...",
      "summary": "..."}]
`side` defaults to RIGHT. Omit `line` for a finding with no single-line anchor.
`summary` is the one-line gist listed under Nuevos in the round body; it
defaults to the body's first line.

replies.json answers questions the author asked on our own earlier threads:
    [{"in_reply_to": 123456789, "body": "..."}]
`in_reply_to` is the id of the comment being answered. A reply whose text is
already on that thread is skipped.

notes.json is a JSON array of already-formatted one-line strings, used only
with --approve:
    ["● `README.md` - el badge apunta al repo anterior."]

summary.json carries what earlier rounds left behind:
    {"resueltos": ["`app/x.rb:42` — N+1 al listar asientos"],
     "pendientes": ["`app/y.rb:10` — redondeo con float (https://...)"],
     "parcial": "security no corrió"}
Every key is optional. `parcial` marks a round whose coverage was reduced.

resolve.json is a JSON array of review-thread node ids to resolve after the
review is published:
    ["PRRT_kwDOAbc123"]

Read-only subcommands print normalized JSON, through REST so they work in
Claude Code cloud sessions, where GraphQL answers 403:
    post_review.py pr --repo owner/name --pr 123       # metadata and file names
    post_review.py diff --repo owner/name --pr 123     # the unified diff
    post_review.py threads --repo owner/name --pr 123  # threads, reviews, PR comments
`threads` tries GraphQL, takes the CCR route (`ccr/review_threads`) when the
session refuses GraphQL, and falls back to REST comments with resolution
unknown. A thread read through CCR has the id `comment:<root comment id>`, and
--resolve resolves it through `ccr/comments/<id>/resolve`.

Requires python3 and an authenticated GitHub CLI. Does not require jq.
"""

import argparse
import json
import re
import subprocess
import sys

# Blocking a merge is never this script's decision, so REQUEST_CHANGES has no
# code path. APPROVE has one, reachable only through --approve.
REVIEW_EVENT = "COMMENT"
APPROVE_EVENT = "APPROVE"

# A 🔵 is an improvement with a concrete alternative; it does not gate a merge,
# so it can ride along with an approval. 🔴 and 🟠 cannot: an approval that
# carries one would contradict itself.
SUGGESTION = "\U0001F535"
BLOCKING_MARKERS = ("\U0001F534", "\U0001F7E0")

# The round body lists findings in words: posted text allows one emoji, the
# marker on the finding itself, and the body is not a finding.
SEVERITY_WORDS = {
    "\U0001F534": "crítico",
    "\U0001F7E0": "importante",
    SUGGESTION: "sugerencia",
}

ROUND_PREFIX = "Ronda "

HUNK = re.compile(r"^@@ .*?\+(\d+)")

THREAD_QUERY = """
query($id: ID!) {
  node(id: $id) {
    ... on PullRequestReviewThread {
      isResolved
      comments(first: 1) { nodes { author { login } body } }
    }
  }
}
"""

THREADS_QUERY = """
query($owner: String!, $repo: String!, $num: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $num) {
      reviewThreads(first: 100) { nodes {
        id isResolved isOutdated path line
        comments(first: 50) { nodes {
          databaseId url author { login } body createdAt } } } }
    }
  }
}
"""

# A thread read through the CCR route has no node id. Its id is its root
# comment's, under this prefix, and it is resolved through that route too.
CCR_THREAD = "comment:"

RESOLVE_MUTATION = """
mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) { thread { isResolved } }
}
"""


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


def graphql_blocked(err):
    """True when GraphQL is refused to this session, not merely failing.

    Claude Code cloud sessions answer every GraphQL call with HTTP 403 and
    point to REST. This is the one place that recognizes it; every GraphQL
    caller asks here before taking the CCR route.
    """
    text = str(err)
    return "403" in text and "not available from Claude Code sessions" in text


PER_PAGE = 100
MAX_PAGES = 100


def gh_pages(endpoint):
    """Every item of a paginated REST list, one `page=N` request at a time.

    Not `gh api --paginate`: it follows GitHub's `Link` header, which names the
    repository by numeric id (`repositories/<id>/...`), and the Claude Code
    cloud proxy refuses those paths with 403 from page 2 on. A page shorter
    than PER_PAGE is the last one.
    """
    joiner = "&" if "?" in endpoint else "?"
    items = []
    for page in range(1, MAX_PAGES + 1):
        batch = json.loads(gh(["api", f"{endpoint}{joiner}per_page={PER_PAGE}"
                                      f"&page={page}"]) or "[]")
        batch = batch if isinstance(batch, list) else [batch]
        items.extend(batch)
        if len(batch) < PER_PAGE:
            return items
    raise RuntimeError(f"{endpoint}: more than {MAX_PAGES} pages")


def pull_request(repo, pr):
    """The PR's REST object. REST, so it works where GraphQL is refused."""
    return json.loads(gh(["api", f"repos/{repo}/pulls/{pr}"]) or "{}")


def pr_diff(repo, pr):
    return gh(["api", f"repos/{repo}/pulls/{pr}",
               "-H", "Accept: application/vnd.github.diff"])


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
            candidate = raw[4:].strip()
            if candidate.startswith("b/"):
                candidate = candidate[2:]
            path = None if candidate in ("/dev/null", "") else candidate
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
        return gh_pages(f"repos/{repo}/pulls/{pr}/comments")
    except RuntimeError as err:
        # Not fatal: without this the run may repost a comment, which is better
        # than refusing to publish at all. Say so plainly.
        print(f"post_review: could not read existing comments ({err}). "
              "Idempotency check skipped.", file=sys.stderr)
        return None


def first_line(body):
    lines = (body or "").splitlines()
    return lines[0] if lines else ""


def opening(body):
    """The prose before any suggestion block: what fails, then the failing case.

    Both lines are needed. A rule violation opens with the quoted rule, so two
    violations of one rule in one file differ only on the second line.
    """
    prose = []
    for line in (body or "").splitlines():
        if line.lstrip().startswith("```"):
            break
        if line.strip():
            prose.append(line.strip())
    return "\n".join(prose[:2])


def posted_signatures(comments):
    """{(path, opening)} for findings this PR already carries.

    The line number is deliberately not part of the key. Between two runs of a
    review the code moves, so the same finding comes back anchored somewhere
    else; keying on the line would let it be posted a second time.
    """
    return {(item.get("path"), opening(item.get("body")))
            for item in comments}


def replied_signatures(comments):
    """{(thread_root_id, first_body_line)} for replies already on a thread.

    GitHub reports every reply with `in_reply_to_id` set to the thread's first
    comment, which is the same id a caller passes as `in_reply_to`.
    """
    return {(item.get("in_reply_to_id"), first_line(item.get("body")))
            for item in comments if item.get("in_reply_to_id")}


def read_json(path, label):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        fail(f"{label} file not found: {path}")
    except json.JSONDecodeError as err:
        fail(f"{label} file is not valid JSON: {err}")


def load_array(path, label):
    if not path:
        return []
    data = read_json(path, label)
    if not isinstance(data, list):
        fail(f"{label} file must contain a JSON array")
    return data


def load_summary(path):
    """{"resueltos": [...], "pendientes": [...], "parcial": str} with defaults."""
    data = read_json(path, "summary") if path else {}
    if not isinstance(data, dict):
        fail("summary file must contain a JSON object")
    clean = lambda items: [str(i).strip() for i in items or [] if str(i).strip()]
    return {"resueltos": clean(data.get("resueltos")),
            "pendientes": clean(data.get("pendientes")),
            "parcial": str(data.get("parcial") or "").strip()}


def head_sha(repo, pr):
    try:
        data = pull_request(repo, pr)
    except RuntimeError as err:
        fail(f"could not read the head commit of PR #{pr} in {repo}: {err}")
    return (data.get("head") or {}).get("sha", "")


def viewer_login():
    """The login this run publishes as, or "" when it cannot be read."""
    try:
        return gh(["api", "user", "--jq", ".login"]).strip()
    except RuntimeError:
        return ""


def our_reviews(repo, pr, login):
    """Reviews this account already left on the PR.

    Fatal when unreadable, and fatal without our login: without them the round
    number counts other reviewers' reviews and their approval passes for ours,
    neither of which can be taken back.
    """
    if not login:
        fail("could not read the login this run publishes as. Nothing sent.")
    try:
        reviews = gh_pages(f"repos/{repo}/pulls/{pr}/reviews")
    except RuntimeError as err:
        fail(f"could not read existing reviews ({err}). Nothing sent.")
    return [item for item in reviews
            if (item.get("user") or {}).get("login") == login]


def is_round(review):
    """A review that counts as a round: it says something, or it approved.

    Answering on a thread makes GitHub create an empty COMMENTED review; that
    is a reply, not a round.
    """
    return bool((review.get("body") or "").strip()) or review.get("state") == "APPROVED"


def next_round(reviews):
    return sum(1 for review in reviews if is_round(review)) + 1


def already_approved(reviews, sha):
    """True when this account already approved this exact head commit."""
    return any(review.get("state") == "APPROVED"
               and (not sha or review.get("commit_id") == sha)
               for review in reviews)


def round_at_head(reviews, sha):
    """True when a round summary already went out at this exact head commit."""
    return any(review.get("commit_id") == sha and is_round(review)
               for review in reviews if sha)


def in_words(text, body):
    """`text` led by the finding's severity in words instead of its marker."""
    for marker, word in SEVERITY_WORDS.items():
        if text.startswith(marker):
            return f"{word}: {text[len(marker):].strip()}"
    for marker, word in SEVERITY_WORDS.items():
        if body.lstrip().startswith(marker):
            return f"{word}: {text}"
    return text


def gist(finding):
    """One line for Nuevos: severity in words, then what fails."""
    body = finding.get("body") or ""
    return in_words((finding.get("summary") or first_line(body)).strip(), body)


def anchor(path, line):
    return f"`{path}:{line}`" if line is not None else f"`{path}`"


def round_body(number, new_lines, summary, notes=None, approving=False, sha=""):
    """The round's review body, or "" when an approval has nothing to say.

    The heading names the head commit reviewed, short and bare so GitHub links
    it, so the author can tell which push a round looked at.

    Sections with nothing in them are left out. An approval with nothing new,
    nothing resolved and no notes goes in bare: the green check already says
    the code was reviewed.
    """
    resolved, pending = summary["resueltos"], summary["pendientes"]
    if approving and not new_lines and not resolved and not notes:
        return ""

    qualifiers = [sha[:7]] if sha else []
    if summary["parcial"]:
        qualifiers.append(f"revisión parcial: {summary['parcial']}")
    heading = f"{ROUND_PREFIX}{number}"
    if qualifiers:
        heading += f" ({', '.join(qualifiers)})"

    if notes:
        plural = "notas" if len(notes) != 1 else "nota"
        status = f"Solo documentación. {len(notes)} {plural}, ninguna bloquea."
    elif new_lines:
        plural = "comentarios nuevos" if len(new_lines) != 1 else "comentario nuevo"
        status = f"{len(new_lines)} {plural}, ninguno bloquea el merge."
    elif resolved or pending:
        status = "Sin comentarios nuevos."
    else:
        status = "Sin comentarios."

    parts = [f"{heading}. {status}"]
    if notes:
        parts.append("\n".join(notes))
    for title, items in (("Nuevos", new_lines),
                         ("Resueltos desde la ronda anterior", resolved),
                         ("Pendientes", pending)):
        if items:
            parts.append(f"{title}:\n" + "\n".join(f"- {item}" for item in items))
    return "\n\n".join(parts)


def reject_blocking_findings(findings):
    """Refuse to approve alongside anything heavier than a suggestion."""
    for finding in findings:
        body = (finding.get("body") or "").lstrip()
        if body.startswith(BLOCKING_MARKERS):
            fail(f"--approve carries only {SUGGESTION} findings. "
                 f"{finding.get('path')} opens with a blocking severity.")
        if not body.startswith(SUGGESTION):
            fail(f"--approve carries only {SUGGESTION} findings. "
                 f"{finding.get('path')} has no severity marker.")


def split_findings(findings, targets, posted):
    """(inline comments, Nuevos lines, already-posted count)."""
    inline, new_lines, skipped = [], [], 0
    for finding in findings:
        path = finding.get("path")
        body = (finding.get("body") or "").strip()
        line = finding.get("line")
        if not path or not body:
            print("post_review: skipping a finding with no path or no body",
                  file=sys.stderr)
            continue
        if (path, opening(body)) in posted:
            skipped += 1
            continue
        if line is not None and (path, int(line)) in targets:
            inline.append({"path": path, "line": int(line),
                           "side": finding.get("side") or "RIGHT",
                           "body": body})
            new_lines.append(f"{anchor(path, line)} — {gist(finding)}")
        else:
            # No hunk to hang it on: the whole finding lives in the body.
            flat = in_words(" ".join(body.split()), body)
            new_lines.append(f"{anchor(path, line)} — {flat} "
                             "(fuera de las líneas del diff)")
    return inline, new_lines, skipped


def unsent_replies(replies, replied):
    """(replies not yet on their thread, already-posted count)."""
    pending, skipped = [], 0
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
        pending.append({"in_reply_to": target, "body": body})
    return pending, skipped


def send_replies(args, pending):
    """Post each reply on its thread. Returns how many failed."""
    failed = 0
    for reply in pending:
        endpoint = (f"repos/{args.repo}/pulls/{args.pr}/comments/"
                    f"{reply['in_reply_to']}/replies")
        try:
            gh(["api", endpoint, "--input", "-"],
               stdin=json.dumps({"body": reply["body"]}))
        except RuntimeError as err:
            failed += 1
            print(f"post_review: reply to comment {reply['in_reply_to']} "
                  f"was rejected.\n{err}", file=sys.stderr)
    return failed


def rest_comment(item):
    return {"id": item.get("id"),
            "author": (item.get("user") or {}).get("login"),
            "body": item.get("body") or "",
            "createdAt": item.get("created_at"),
            "url": item.get("html_url")}


def graphql_threads(repo, pr):
    owner, name = repo.split("/", 1)
    raw = gh(["api", "graphql", "-f", f"query={THREADS_QUERY}",
              "-F", f"owner={owner}", "-F", f"repo={name}", "-F", f"num={pr}"])
    pull = (((json.loads(raw or "{}").get("data") or {}).get("repository") or {})
            .get("pullRequest") or {})
    threads = []
    for node in (pull.get("reviewThreads") or {}).get("nodes") or []:
        threads.append({
            "id": node.get("id"),
            "isResolved": bool(node.get("isResolved")),
            "isOutdated": bool(node.get("isOutdated")),
            "path": node.get("path"),
            "line": node.get("line"),
            "comments": [{"id": c.get("databaseId"),
                          "author": (c.get("author") or {}).get("login"),
                          "body": c.get("body") or "",
                          "createdAt": c.get("createdAt"),
                          "url": c.get("url")}
                         for c in (node.get("comments") or {}).get("nodes") or []],
        })
    return threads


def normalize_ccr(raw_threads, rest_comments):
    """CCR threads in the shape the GraphQL query yields.

    `ccr/review_threads` answers
        [{"resolved": bool, "outdated": bool, "path": str, "line": int|null,
          "comment_ids": [int, ...]}]
    with no node id, authors, or bodies. `comment_ids[0]` is the root and the
    rest are replies in order, so each id is filled in from the REST comments.
    The root id, prefixed with CCR_THREAD, stands in for the thread id. `line`
    is null on an outdated thread and stays null. An id REST does not return
    is dropped and reported, never fatal.
    """
    by_id = {item.get("id"): item for item in rest_comments}
    threads = []
    for raw in raw_threads:
        ids = raw.get("comment_ids") or []
        missing = [cid for cid in ids if cid not in by_id]
        if missing:
            print(f"post_review: CCR thread on {raw.get('path')} names comments "
                  f"REST does not return: {missing}. Ignored.", file=sys.stderr)
        threads.append({
            "id": f"{CCR_THREAD}{ids[0]}" if ids else None,
            "isResolved": bool(raw.get("resolved")),
            "isOutdated": bool(raw.get("outdated")),
            "path": raw.get("path"),
            "line": raw.get("line"),
            "comments": [rest_comment(by_id[cid]) for cid in ids if cid in by_id],
        })
    return threads


def rest_threads(rest_comments):
    """Threads rebuilt from REST comments: no thread id, no resolution state."""
    roots, replies = [], {}
    for item in rest_comments:
        parent = item.get("in_reply_to_id")
        if parent:
            replies.setdefault(parent, []).append(item)
        else:
            roots.append(item)
    threads = []
    for root in roots:
        chain = [root] + sorted(replies.get(root.get("id"), []),
                                key=lambda c: c.get("created_at") or "")
        threads.append({"id": None, "isResolved": False, "isOutdated": None,
                        "path": root.get("path"), "line": root.get("line"),
                        "comments": [rest_comment(c) for c in chain]})
    return threads


def read_threads(repo, pr):
    """(source, threads): GraphQL, then CCR when GraphQL is refused, then REST.

    Only the cloud-session refusal takes the CCR route. Any other GraphQL
    failure, or a CCR failure, falls to REST, where resolution is unknown.
    """
    try:
        return "graphql", graphql_threads(repo, pr)
    except RuntimeError as err:
        blocked = graphql_blocked(err)
        if not blocked:
            print(f"post_review: GraphQL failed ({err}).", file=sys.stderr)
    rest = gh_pages(f"repos/{repo}/pulls/{pr}/comments")
    if blocked:
        try:
            raw = json.loads(gh(["api", f"repos/{repo}/pulls/{pr}/ccr/review_threads"])
                             or "[]")
            return "ccr", normalize_ccr(raw, rest)
        except (RuntimeError, ValueError) as err:
            print(f"post_review: CCR review threads failed ({err}).", file=sys.stderr)
    print("post_review: resolution state unknown; every thread is treated as "
          "unresolved.", file=sys.stderr)
    return "rest", rest_threads(rest)


def ccr_thread(repo, pr, thread_id, cache):
    """The normalized CCR thread whose id is `thread_id`, or None."""
    if "threads" not in cache:
        rest = gh_pages(f"repos/{repo}/pulls/{pr}/comments")
        raw = json.loads(gh(["api", f"repos/{repo}/pulls/{pr}/ccr/review_threads"])
                         or "[]")
        cache["threads"] = {t["id"]: t for t in normalize_ccr(raw, rest)}
    return cache["threads"].get(thread_id)


def thread_root(repo, pr, thread_id, cache):
    """(isResolved, root author, root body) for one thread id.

    A CCR id reads the CCR listing; any other id is a GraphQL node.
    """
    if thread_id.startswith(CCR_THREAD):
        found = ccr_thread(repo, pr, thread_id, cache)
        if found is None:
            raise RuntimeError("not among the CCR review threads")
        root = (found["comments"] or [{}])[0]
        return found["isResolved"], root.get("author"), root.get("body") or ""
    raw = gh(["api", "graphql", "-f", f"query={THREAD_QUERY}",
              "-F", f"id={thread_id}"])
    node = (json.loads(raw or "{}").get("data") or {}).get("node") or {}
    roots = (node.get("comments") or {}).get("nodes") or [{}]
    return (node.get("isResolved"), (roots[0].get("author") or {}).get("login"),
            roots[0].get("body") or "")


def resolvable_threads(repo, pr, ids, login):
    """The subset of thread ids that are open and were opened by us."""
    keep, cache = [], {}
    for thread_id in ids:
        try:
            resolved, author, body = thread_root(repo, pr, thread_id, cache)
        except (RuntimeError, ValueError) as err:
            print(f"post_review: could not read thread {thread_id} ({err}). "
                  "Not resolving it.", file=sys.stderr)
            continue
        body = body.lstrip()
        if resolved:
            continue
        if not login or author != login or not body.startswith(tuple(SEVERITY_WORDS)):
            print(f"post_review: thread {thread_id} was not opened by this "
                  "review. Not resolving it.", file=sys.stderr)
            continue
        keep.append(thread_id)
    return keep


def resolve_thread(repo, pr, thread_id):
    """GraphQL for a node id; the CCR route for a CCR id."""
    if thread_id.startswith(CCR_THREAD):
        comment_id = thread_id[len(CCR_THREAD):]
        gh(["api", "-X", "POST",
            f"repos/{repo}/pulls/{pr}/ccr/comments/{comment_id}/resolve"])
        return
    gh(["api", "graphql", "-f", f"query={RESOLVE_MUTATION}",
        "-F", f"id={thread_id}"])


def resolve_threads(repo, pr, ids):
    """Resolve each thread. Returns how many failed."""
    failed = 0
    for thread_id in ids:
        try:
            resolve_thread(repo, pr, thread_id)
        except RuntimeError as err:
            failed += 1
            print(f"post_review: thread {thread_id} could not be resolved.\n{err}",
                  file=sys.stderr)
    return failed


def send_review(args, payload, label):
    try:
        response = gh(
            ["api", f"repos/{args.repo}/pulls/{args.pr}/reviews", "--input", "-"],
            stdin=json.dumps(payload),
        )
    except RuntimeError as err:
        print(f"post_review: the API rejected the {label}. Nothing was "
              f"published.\n{err}", file=sys.stderr)
        print("post_review: payload kept for inspection:", file=sys.stderr)
        print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    return json.loads(response or "{}").get("html_url", "")


def run_approve(args):
    """Approve a pull request the caller has already decided is approvable.

    Two shapes. A docs-only run carries its notes as prose in the body. A run
    whose only surviving findings are suggestions carries them inline, since a
    suggestion does not gate the merge the approval just cleared.
    """
    notes = [str(n).strip() for n in load_array(args.notes, "notes")
             if str(n).strip()]
    findings = load_array(args.findings, "findings")
    replies = load_array(args.replies, "replies")
    summary = load_summary(args.summary)
    resolve = load_array(args.resolve, "resolve")
    reject_blocking_findings(findings)
    if summary["pendientes"]:
        fail("--approve refuses pending threads: an approval cannot go out "
             "while a problem is still open.")
    if summary["parcial"]:
        fail("--approve refuses a partial round: reduced coverage is approved "
             "by a human, not by this script.")

    try:
        gh(["auth", "status"])
    except RuntimeError:
        fail("gh is not authenticated. Run: gh auth login")

    sha = head_sha(args.repo, args.pr)
    login = viewer_login()
    reviews = our_reviews(args.repo, args.pr, login)

    if already_approved(reviews, sha):
        print(f"post_review: PR #{args.pr} is already approved at "
              f"{sha[:7] or 'its head commit'}. Nothing sent.")
        return

    inline, new_lines, pending_replies = [], [], []
    if findings or replies:
        comments = existing_comments(args.repo, args.pr)
        known = comments if comments is not None else []
        pending_replies, _ = unsent_replies(replies, replied_signatures(known))
    if findings:
        try:
            patch = pr_diff(args.repo, args.pr)
        except RuntimeError as err:
            fail(f"could not read the diff for PR #{args.pr} in {args.repo}: {err}")
        inline, new_lines, _ = split_findings(
            findings, commentable_lines(patch), posted_signatures(known))

    number = next_round(reviews)
    payload = {"event": APPROVE_EVENT}
    body = round_body(number, new_lines, summary, notes=notes, approving=True,
                      sha=sha)
    if body:
        payload["body"] = body
    if inline:
        payload["comments"] = inline
    if sha:
        payload["commit_id"] = sha

    threads = resolvable_threads(args.repo, args.pr, resolve, login)
    counters = (f"round={number} notes={len(notes)} inline={len(inline)} "
                f"degraded={len(new_lines) - len(inline)} "
                f"replies={len(pending_replies)} resolve={len(threads)}")

    if args.dry_run:
        print("post_review: dry run. The approval was NOT sent. Payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if pending_replies:
            print("post_review: replies that would be sent first:")
            print(json.dumps(pending_replies, indent=2, ensure_ascii=False))
        if threads:
            print("post_review: threads that would be resolved:")
            print(json.dumps(threads, indent=2))
        print(f"post_review: {counters} approve=not-sent")
        return

    # The answer reaches the author before the approval does, so the approval
    # never reads as closing a question nobody answered.
    failed = send_replies(args, pending_replies)
    url = send_review(args, payload, "approval")
    failed += resolve_threads(args.repo, args.pr, threads)
    print(f"post_review: published as {APPROVE_EVENT} — {counters}")
    if url:
        print(f"post_review: {url}")
    if failed:
        print(f"post_review: {failed} reply(ies) or thread(s) failed. The "
              "approval itself was published.", file=sys.stderr)
        sys.exit(1)


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def read_command(name, argv):
    """`pr`, `diff`, `threads`: read-only, REST first, JSON on stdout."""
    parser = argparse.ArgumentParser(prog=f"post_review.py {name}")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pr", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        if name == "diff":
            sys.stdout.write(pr_diff(args.repo, args.pr))
        elif name == "pr":
            data = pull_request(args.repo, args.pr)
            files = gh_pages(f"repos/{args.repo}/pulls/{args.pr}/files")
            show({"number": data.get("number"), "title": data.get("title"),
                  "body": data.get("body") or "",
                  "author": (data.get("user") or {}).get("login"),
                  "authorIsBot": (data.get("user") or {}).get("type") == "Bot",
                  "draft": bool(data.get("draft")),
                  "base": (data.get("base") or {}).get("ref"),
                  "head": (data.get("head") or {}).get("ref"),
                  "headSha": (data.get("head") or {}).get("sha"),
                  "url": data.get("html_url"),
                  "files": [f.get("filename") for f in files]})
        else:
            source, threads = read_threads(args.repo, args.pr)
            reviews = gh_pages(f"repos/{args.repo}/pulls/{args.pr}/reviews")
            issue = gh_pages(f"repos/{args.repo}/issues/{args.pr}/comments")
            show({"source": source,
                  "resolution": "unknown" if source == "rest" else "known",
                  "threads": threads,
                  "reviews": [{"id": r.get("id"),
                               "author": (r.get("user") or {}).get("login"),
                               "state": r.get("state"), "body": r.get("body") or "",
                               "commitId": r.get("commit_id"),
                               "submittedAt": r.get("submitted_at")}
                              for r in reviews],
                  "issueComments": [rest_comment(c) for c in issue]})
    except RuntimeError as err:
        fail(f"could not read {name} for PR #{args.pr} in {args.repo}: {err}")


READ_COMMANDS = ("pr", "diff", "threads")


def main():
    if len(sys.argv) > 1 and sys.argv[1] in READ_COMMANDS:
        read_command(sys.argv[1], sys.argv[2:])
        return
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--findings", help="JSON array file")
    parser.add_argument("--replies", help="JSON array file")
    parser.add_argument("--notes", help="JSON array of strings, with --approve")
    parser.add_argument("--summary", help="JSON object: resueltos, pendientes, parcial")
    parser.add_argument("--resolve", help="JSON array of review-thread ids")
    parser.add_argument("--approve", action="store_true",
                        help="approve a diff the caller found approvable")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.approve:
        if args.findings and args.notes:
            fail("--approve takes --findings or --notes, not both: inline "
                 "suggestions and docs-only notes are different runs.")
        run_approve(args)
        return

    if args.notes:
        fail("--notes is only meaningful with --approve")

    if not (args.findings or args.replies or args.summary or args.resolve):
        fail("nothing to do: pass --findings, --replies, --summary, or --resolve")

    findings = load_array(args.findings, "findings")
    replies = load_array(args.replies, "replies")
    summary = load_summary(args.summary)
    resolve = load_array(args.resolve, "resolve")

    try:
        gh(["auth", "status"])
    except RuntimeError:
        fail("gh is not authenticated. Run: gh auth login")

    targets = set()
    if findings:
        try:
            patch = pr_diff(args.repo, args.pr)
        except RuntimeError as err:
            fail(f"could not read the diff for PR #{args.pr} in {args.repo}: {err}")
        targets = commentable_lines(patch)

    comments = existing_comments(args.repo, args.pr)
    posted = posted_signatures(comments) if comments is not None else set()
    replied = replied_signatures(comments) if comments is not None else set()

    inline, new_lines, skipped = split_findings(findings, targets, posted)

    pending_replies, skipped_replies = unsent_replies(replies, replied)
    skipped += skipped_replies

    sha = head_sha(args.repo, args.pr)
    login = viewer_login()
    reviews = our_reviews(args.repo, args.pr, login)
    number = next_round(reviews)
    threads = resolvable_threads(args.repo, args.pr, resolve, login)

    # A round with nothing new at a commit that already has one would only
    # notify the author twice about the same code.
    payload = None
    if new_lines or not round_at_head(reviews, sha):
        payload = {"event": REVIEW_EVENT,
                   "body": round_body(number, new_lines, summary, sha=sha),
                   "comments": inline}
        if sha:
            payload["commit_id"] = sha

    if payload is None and not pending_replies and not threads:
        print(f"post_review: a round already went out at {sha[:7]} and nothing "
              f"new remains (already-posted={skipped}). No review created.")
        return

    counters = (f"round={number if payload else '-'} inline={len(inline)} "
                f"degraded={len(new_lines) - len(inline)} "
                f"replies={len(pending_replies)} resolve={len(threads)} "
                f"already-posted={skipped}")

    if args.dry_run:
        if payload is not None:
            print("post_review: dry run. Payload that would be sent:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("post_review: dry run. No review would be created.")
        if pending_replies:
            print("post_review: replies that would be sent:")
            print(json.dumps(pending_replies, indent=2, ensure_ascii=False))
        if threads:
            print("post_review: threads that would be resolved:")
            print(json.dumps(threads, indent=2))
        print(f"post_review: {counters}")
        return

    url = send_review(args, payload, "review") if payload is not None else ""

    failed = send_replies(args, pending_replies) + resolve_threads(args.repo, args.pr, threads)

    print(f"post_review: published as {REVIEW_EVENT} — {counters}")
    if url:
        print(f"post_review: {url}")
    if failed:
        print(f"post_review: {failed} reply(ies) or thread(s) failed. The "
              "review itself was published.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
