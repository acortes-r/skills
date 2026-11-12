#!/usr/bin/env python3
"""Tests for scripts/post_review.py. No network, no dependencies, no pytest.

    python3 skills/review-changes/tests/test_post_review.py

Every test replaces the module's `gh` with a stub, so nothing reaches GitHub.
A failure prints the case that broke and exits non-zero.
"""

import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PUBLISHER = HERE.parent / "scripts" / "post_review.py"


def load_publisher():
    spec = importlib.util.spec_from_file_location("post_review", PUBLISHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load_publisher()
TMP = pathlib.Path(tempfile.mkdtemp(prefix="post_review_tests_"))

DIFF = """--- a/app/models/user.rb
+++ b/app/models/user.rb
@@ -48,6 +48,8 @@ class User
   def notify
+    user = User.find_by(id: id)
+    notify(user.email)
   end
"""

FINDING_BODY = "🟠 `user` puede ser nil — `find_by` devuelve nil."
REPLY_BODY = "El retry viene del webhook, no del cliente."
HEAD = "abc1234def5678"
PULL = {"number": 1, "title": "Agrega avisos de reserva", "body": "",
        "user": {"login": "autora-ficticia", "type": "User"}, "draft": False,
        "base": {"ref": "main"}, "head": {"ref": "feat/avisos", "sha": HEAD},
        "html_url": "https://example.test/o/n/pull/1"}

failures = []


def write(name, data):
    path = TMP / name
    path.write_text(json.dumps(data, ensure_ascii=False))
    return str(path)


OURS = {"login": "revisora-ficticia"}


def thread(author="revisora-ficticia", body=FINDING_BODY, resolved=False):
    return {"isResolved": resolved,
            "comments": {"nodes": [{"author": {"login": author}, "body": body}]}}


BLOCKED = ("gh: GitHub GraphQL is not available from Claude Code sessions; "
           "use the REST API (HTTP 403)")


def run(argv, comments=None, reviews=None, sent=None, threads=None,
        graphql="ok", review_threads=None, ccr=None, sub=None):
    """Run main() with a stubbed gh. Returns everything it printed.

    `graphql` is "ok", "blocked" (the cloud-session 403), or "error". `ccr` is
    the `ccr/review_threads` answer; None makes that route fail.
    """
    sent = sent if sent is not None else []

    def fake_gh(args, stdin=None):
        if args[:2] == ["auth", "status"]:
            return ""
        if args[:2] == ["api", "graphql"]:
            if graphql == "blocked":
                raise RuntimeError(BLOCKED)
            if graphql == "error":
                raise RuntimeError("gh: Something went wrong (HTTP 502)")
            query = next(a for a in args if a.startswith("query="))
            if "reviewThreads" in query:
                return json.dumps({"data": {"repository": {"pullRequest": {
                    "reviewThreads": {"nodes": review_threads or []}}}}})
            thread_id = next(a for a in args if a.startswith("id="))[3:]
            if "resolveReviewThread" in query:
                sent.append({"resolve": thread_id})
                return "{}"
            return json.dumps({"data": {"node": (threads or {}).get(thread_id)}})
        if args[:2] == ["api", "user"]:
            return "revisora-ficticia\n"
        if args[0] != "api":
            raise AssertionError(f"unexpected gh call: {args!r}")
        endpoint = next(a for a in args[1:] if not a.startswith("-")
                        and a not in ("POST", "Accept: application/vnd.github.diff"))
        if endpoint.endswith("/ccr/review_threads"):
            if ccr is None:
                raise RuntimeError("gh: Not Found (HTTP 404)")
            return json.dumps(ccr)
        if "/ccr/comments/" in endpoint and endpoint.endswith("/resolve"):
            sent.append({"ccr_resolve": endpoint.split("/")[-2]})
            return "{}"
        if endpoint == "repos/o/n/pulls/1":
            if "Accept: application/vnd.github.diff" in args:
                return DIFF
            return json.dumps(PULL)
        if endpoint.endswith("/files"):
            return json.dumps([{"filename": "app/models/user.rb"}])
        if endpoint.startswith("repos/o/n/issues/"):
            return "[]"
        if endpoint.endswith("/replies"):
            sent.append({"reply": json.loads(stdin)})
            return "{}"
        if endpoint.endswith("/comments"):
            return json.dumps(comments or [])
        if endpoint.endswith("/reviews"):
            if stdin is None:
                return json.dumps(reviews or [])
            sent.append(json.loads(stdin))
            return json.dumps({"html_url": "https://example.test/r/1"})
        raise AssertionError(f"unexpected gh call: {args!r}")

    original, mod.gh = mod.gh, fake_gh
    head = [sub] if sub else []
    sys.argv = ["post_review.py"] + head + ["--repo", "o/n", "--pr", "1"] + argv
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            try:
                mod.main()
            except SystemExit as exit_signal:
                buffer.write(f"EXIT {exit_signal.code}")
    finally:
        mod.gh = original
    return buffer.getvalue()


def check(name, condition, output):
    if condition:
        print(f"  ok   {name}")
    else:
        failures.append(name)
        print(f"  FAIL {name}\n{output}")


# --- idempotency -------------------------------------------------------

def test_moved_finding_is_not_reposted():
    """The same finding, now on another line after a rebase, is not reposted."""
    existing = [{"path": "app/models/user.rb", "line": 42, "id": 111,
                 "body": FINDING_BODY, "in_reply_to_id": None}]
    findings = write("f.json", [{"path": "app/models/user.rb", "line": 51,
                                 "body": FINDING_BODY}])
    at_head = [{"state": "COMMENTED", "commit_id": HEAD, "user": OURS,
                "body": "Ronda 1. 1 comentario nuevo, ninguno bloquea el merge."}]
    sent = []
    out = run(["--findings", findings], comments=existing, reviews=at_head,
              sent=sent)
    check("a finding whose code moved lines is not reposted",
          "already-posted=1" in out and "No review created" in out
          and not sent, out)


def test_second_violation_of_the_same_rule_is_published():
    """Two violations of one rule share the quoted rule line, not the failure."""
    rule = '🟠 `CLAUDE.md` · Errores: "toda llamada externa lleva timeout".'
    existing = [{"path": "app/models/user.rb", "line": 42, "id": 112,
                 "body": rule + "\nEste `Faraday.get` no lo tiene.",
                 "in_reply_to_id": None}]
    findings = write("f_rule.json", [{"path": "app/models/user.rb", "line": 50,
                                      "body": rule + "\nEste `Net::HTTP.get` no lo tiene."}])
    out = run(["--findings", findings, "--dry-run"], comments=existing)
    check("a second violation of an already-cited rule is published",
          "inline=1" in out and "already-posted=0" in out, out)


def test_a_deleted_file_offers_no_targets():
    patch = ("--- a/app/legacy.rb\n+++ /dev/null\n@@ -1,2 +0,0 @@\n"
             "-def old\n-end\n" + DIFF)
    targets = mod.commentable_lines(patch)
    check("a deleted file adds no path to the targets",
          {path for path, _ in targets} == {"app/models/user.rb"}, targets)


def test_new_finding_is_published():
    findings = write("f2.json", [{"path": "app/models/user.rb", "line": 51,
                                  "body": "🔵 Extrae el timeout a constante."}])
    out = run(["--findings", findings, "--dry-run"])
    check("a finding with no earlier thread is published",
          '"line": 51' in out and "inline=1" in out and "already-posted=0" in out, out)


def test_duplicate_reply_is_skipped():
    existing = [
        {"path": "app/models/user.rb", "line": 42, "id": 111,
         "body": FINDING_BODY, "in_reply_to_id": None},
        {"path": "app/models/user.rb", "line": 42, "id": 113,
         "body": REPLY_BODY, "in_reply_to_id": 111},
    ]
    replies = write("r.json", [{"in_reply_to": 111, "body": REPLY_BODY}])
    sent = []
    out = run(["--replies", replies, "--dry-run"], comments=existing, sent=sent)
    check("a reply already on the thread is skipped",
          "already-posted=1" in out and "replies=0" in out and not sent, out)


def test_a_reply_at_a_head_with_a_round_creates_no_review():
    existing = [{"path": "app/models/user.rb", "line": 42, "id": 111,
                 "body": FINDING_BODY, "in_reply_to_id": None}]
    at_head = [{"state": "COMMENTED", "commit_id": HEAD, "user": OURS,
                "body": "Ronda 1. Sin comentarios."}]
    replies = write("r2.json", [{"in_reply_to": 111,
                                 "body": "Stripe reintenta el mismo event.id."}])
    out = run(["--replies", replies, "--dry-run"], comments=existing,
              reviews=at_head)
    check("a reply at a head that already has a round creates no review",
          '"in_reply_to": 111' in out and "replies=1" in out
          and "No review would be created" in out, out)


def test_nothing_at_all_is_refused():
    out = run([])
    check("no input at all is refused",
          "nothing to do" in out and "EXIT 1" in out, out)


# --- rounds ------------------------------------------------------------

def test_first_round_lists_new_findings_without_emoji():
    findings = write("f7.json", [{"path": "app/models/user.rb", "line": 51,
                                  "body": FINDING_BODY,
                                  "summary": "`user` puede ser nil"}])
    sent = []
    out = run(["--findings", findings], sent=sent)
    body = sent[0]["body"] if sent else ""
    check("the first round names Ronda 1, its commit, and lists Nuevos in words",
          body.startswith("Ronda 1 (abc1234). 1 comentario nuevo")
          and "- `app/models/user.rb:51` — importante: `user` puede ser nil" in body
          and "Resueltos" not in body and "Pendientes" not in body
          and "🟠" not in body, out)


def test_round_number_counts_only_our_rounds():
    reviews = [
        {"state": "COMMENTED", "commit_id": "old1", "user": OURS,
         "body": "Ronda 1. 2 comentarios nuevos, ninguno bloquea el merge."},
        {"state": "COMMENTED", "commit_id": "old1", "user": OURS, "body": ""},
        {"state": "APPROVED", "commit_id": "old2", "user": OURS, "body": ""},
        {"state": "COMMENTED", "commit_id": "old2",
         "user": {"login": "otra-cuenta-ficticia"}, "body": "Se ve bien."},
    ]
    sent = []
    out = run(["--summary", write("s.json", {"pendientes": ["`a.rb:3` — x"]})],
              reviews=reviews, sent=sent)
    body = sent[0]["body"] if sent else ""
    check("a reply's empty review and another account's review are not rounds",
          body.startswith("Ronda 3 (abc1234). Sin comentarios nuevos.")
          and "Pendientes:\n- `a.rb:3` — x" in body, out)


def test_summary_only_round_is_sent_once_per_head():
    at_head = [{"state": "COMMENTED", "commit_id": HEAD, "user": OURS,
                "body": "Ronda 1. Sin comentarios."}]
    sent = []
    out = run(["--summary", write("s2.json", {})], reviews=at_head, sent=sent)
    check("a second summary at the same head commit is not sent",
          "already went out" in out and not sent, out)


def test_partial_round_says_so():
    sent = []
    out = run(["--summary", write("s3.json", {"parcial": "security no corrió"})],
              sent=sent)
    check("a partial round names what did not run",
          sent and sent[0]["body"]
          == "Ronda 1 (abc1234, revisión parcial: security no corrió). Sin comentarios.", out)


def test_degraded_finding_lives_in_the_list():
    findings = write("f8.json", [{"path": "app/models/user.rb", "line": 5,
                                  "body": "🔵 Extrae el timeout\na constante."}])
    sent = []
    out = run(["--findings", findings], sent=sent)
    body = sent[0]["body"] if sent else ""
    check("a finding outside the diff is listed whole, in words",
          "`app/models/user.rb:5` — sugerencia: Extrae el timeout a constante. "
          "(fuera de las líneas del diff)" in body
          and sent[0]["comments"] == [], out)


# --- resolving threads -------------------------------------------------

def test_only_our_open_threads_are_resolved():
    threads = {"T1": thread(), "T2": thread(author="otra-cuenta-ficticia"),
               "T3": thread(resolved=True), "T4": thread(body="Comentario a mano.")}
    sent = []
    out = run(["--summary", write("s4.json", {"resueltos": ["`a.rb:1` — x"]}),
               "--resolve", write("t.json", ["T1", "T2", "T3", "T4"])],
              sent=sent, threads=threads)
    resolved = [item["resolve"] for item in sent if "resolve" in item]
    check("only open threads this review opened are resolved",
          resolved == ["T1"] and "resolve=1" in out, out)


def test_dry_run_resolves_nothing():
    sent = []
    out = run(["--resolve", write("t2.json", ["T1"]), "--dry-run"],
              sent=sent, threads={"T1": thread()})
    check("--dry-run lists the threads but resolves none",
          "threads that would be resolved" in out and not sent, out)


# --- approve -----------------------------------------------------------

NOTES = ["🔵 `README.md` — el badge apunta al repo anterior."]


def test_approve_dry_run_sends_nothing():
    sent = []
    out = run(["--approve", "--notes", write("n.json", NOTES), "--dry-run"], sent=sent)
    check("approve --dry-run sends nothing",
          "NOT sent" in out and '"event": "APPROVE"' in out and not sent, out)


def test_approve_pins_the_head_commit():
    sent = []
    out = run(["--approve", "--notes", write("n.json", NOTES)], sent=sent)
    check("approve pins the head commit it approved",
          len(sent) == 1 and sent[0].get("commit_id") == HEAD
          and sent[0]["event"] == "APPROVE", out)


def test_approve_with_no_notes_carries_no_body():
    sent = []
    out = run(["--approve"], sent=sent)
    check("approve with no notes carries no body at all",
          len(sent) == 1 and "body" not in sent[0], out)


def test_the_same_head_is_never_approved_twice():
    existing = [{"state": "APPROVED", "commit_id": HEAD,
                 "user": {"login": "revisora-ficticia"}}]
    sent = []
    out = run(["--approve", "--notes", write("n.json", NOTES)],
              reviews=existing, sent=sent)
    check("the same head commit is never approved twice",
          "already approved" in out and not sent, out)


def test_an_approval_by_someone_else_does_not_block_ours():
    existing = [{"state": "APPROVED", "commit_id": HEAD,
                 "user": {"login": "otra-cuenta-ficticia"}}]
    sent = []
    out = run(["--approve"], reviews=existing, sent=sent)
    check("another account's approval does not count as ours",
          len(sent) == 1, out)


def test_approve_carries_a_suggestion_inline():
    findings = write("f3.json", [{"path": "app/models/user.rb", "line": 51,
                                  "body": "🔵 Extrae el timeout a constante."}])
    sent = []
    out = run(["--approve", "--findings", findings], sent=sent)
    sole = sent[0] if sent else {}
    check("approve carries a suggestion inline",
          sole.get("event") == "APPROVE"
          and sole.get("comments", [{}])[0].get("line") == 51
          and sole.get("body") == (
              "Ronda 1 (abc1234). 1 comentario nuevo, ninguno bloquea el merge.\n\n"
              "Nuevos:\n- `app/models/user.rb:51` — sugerencia: "
              "Extrae el timeout a constante."),
          out)


def test_approve_with_resolved_threads_lists_them():
    reviews = [{"state": "COMMENTED", "commit_id": "old1", "user": OURS,
                "body": "Ronda 1. 1 comentario nuevo, ninguno bloquea el merge."}]
    sent = []
    out = run(["--approve",
               "--summary", write("s5.json", {"resueltos": ["`a.rb:1` — N+1"]}),
               "--resolve", write("t3.json", ["T1"])],
              reviews=reviews, sent=sent, threads={"T1": thread()})
    review = next((item for item in sent if "event" in item), {})
    check("an approval after fixes names the round and what was resolved",
          review.get("event") == "APPROVE"
          and review.get("body") == ("Ronda 2 (abc1234). Sin comentarios nuevos.\n\n"
                                     "Resueltos desde la ronda anterior:\n"
                                     "- `a.rb:1` — N+1")
          and {"resolve": "T1"} in sent, out)


def test_approve_refuses_pending_threads():
    sent = []
    out = run(["--approve",
               "--summary", write("s6.json", {"pendientes": ["`a.rb:1` — x"]})],
              sent=sent)
    check("approve refuses a round with pending threads",
          "pending threads" in out and "EXIT 1" in out and not sent, out)


def test_approve_refuses_a_partial_round():
    sent = []
    out = run(["--approve", "--summary", write("s7.json", {"parcial": "verify"})],
              sent=sent)
    check("approve refuses a partial round",
          "partial round" in out and "EXIT 1" in out and not sent, out)


def test_approve_sends_the_reply_first():
    existing = [{"path": "app/models/user.rb", "line": 42, "id": 111,
                 "body": FINDING_BODY, "in_reply_to_id": None}]
    sent = []
    out = run(["--approve", "--replies",
               write("r3.json", [{"in_reply_to": 111, "body": REPLY_BODY}])],
              comments=existing, sent=sent)
    check("an owed reply goes out before the approval, in one run",
          len(sent) == 2 and "reply" in sent[0]
          and sent[1].get("event") == "APPROVE", out)


def test_approve_refuses_a_blocking_finding():
    findings = write("f4.json", [{"path": "app/models/user.rb", "line": 51,
                                  "body": "🟠 `user` puede ser nil."}])
    sent = []
    out = run(["--approve", "--findings", findings], sent=sent)
    check("approve refuses an important finding",
          "blocking severity" in out and "EXIT 1" in out and not sent, out)


def test_approve_refuses_a_finding_with_no_severity():
    findings = write("f5.json", [{"path": "app/models/user.rb", "line": 51,
                                  "body": "Extrae el timeout a constante."}])
    sent = []
    out = run(["--approve", "--findings", findings], sent=sent)
    check("approve refuses a finding with no severity marker",
          "no severity marker" in out and "EXIT 1" in out and not sent, out)


def test_approve_refuses_findings_and_notes_together():
    findings = write("f6.json", [{"path": "a.rb", "line": 1, "body": "🔵 x."}])
    sent = []
    out = run(["--approve", "--findings", findings,
               "--notes", write("n.json", NOTES)], sent=sent)
    check("approve takes findings or notes, not both",
          "not both" in out and "EXIT 1" in out and not sent, out)


def without_login(argv, reviews):
    """Run with the publishing account unreadable."""
    original, mod.viewer_login = mod.viewer_login, lambda: ""
    try:
        sent = []
        return run(argv, reviews=reviews, sent=sent), sent
    finally:
        mod.viewer_login = original


def test_unknown_login_sends_nothing():
    """Without our login, someone else's reviews would pass for ours."""
    theirs = [{"state": "APPROVED", "commit_id": HEAD,
               "user": {"login": "otra-cuenta-ficticia"}, "body": ""}]
    findings = write("f_login.json", [{"path": "app/models/user.rb", "line": 51,
                                       "body": "🟠 `user` puede ser nil."}])
    out, sent = without_login(["--findings", findings], theirs)
    check("an unknown login stops a review before sending",
          "EXIT 1" in out and "login" in out and not sent, out)
    out, sent = without_login(["--approve"], theirs)
    check("an unknown login stops an approval before sending",
          "EXIT 1" in out and "login" in out and not sent, out)


def test_notes_require_approve():
    out = run(["--notes", write("n.json", NOTES)])
    check("--notes without --approve is refused",
          "only meaningful with --approve" in out and "EXIT 1" in out, out)


# --- what --auto reads from the publisher ------------------------------
# An unattended run has no human to read the payload, so it acts on the exit
# code and the printed lines. These pin that contract.


def test_refused_approval_dry_run_sends_nothing():
    findings = write("f_auto1.json", [{"path": "app/models/user.rb", "line": 51,
                                       "body": "🔵 Extrae el timeout a constante."}])
    summary = write("s_auto1.json", {"pendientes": ["`a.rb:1` — x"]})
    sent = []
    out = run(["--approve", "--findings", findings, "--summary", summary,
               "--dry-run"], sent=sent)
    check("a refused approval fails its dry run before any write",
          "--approve refuses" in out and "EXIT 1" in out and not sent, out)


def test_refused_approval_falls_back_to_comment():
    findings = write("f_auto2.json", [{"path": "app/models/user.rb", "line": 51,
                                       "body": "🔵 Extrae el timeout a constante."}])
    summary = write("s_auto2.json", {"pendientes": ["`a.rb:1` — x"]})
    sent = []
    out = run(["--findings", findings, "--summary", summary], sent=sent)
    sole = sent[0] if sent else {}
    check("the same round without --approve goes out as COMMENT",
          len(sent) == 1 and sole.get("event") == "COMMENT"
          and sole.get("comments", [{}])[0].get("line") == 51
          and "EXIT" not in out, out)


def test_a_sent_review_prints_its_url():
    findings = write("f_auto3.json", [{"path": "app/models/user.rb", "line": 51,
                                       "body": "🔵 Extrae el timeout a constante."}])
    approved = run(["--approve", "--findings", findings])
    commented = run(["--findings", findings])
    check("an approval prints its round and url",
          "published as APPROVE" in approved and "round=1" in approved
          and "post_review: https://example.test/r/1" in approved, approved)
    check("a COMMENT round prints its round and url",
          "published as COMMENT" in commented and "round=1" in commented
          and "post_review: https://example.test/r/1" in commented, commented)


def test_nothing_new_at_head_exits_clean():
    at_head = [{"state": "COMMENTED", "commit_id": HEAD, "user": OURS,
                "body": "Ronda 1 (abc1234). Sin comentarios."}]
    sent = []
    out = run(["--summary", write("s_auto4.json", {})], reviews=at_head, sent=sent)
    check("nothing new at a head with a round exits 0 and says so",
          "No review created" in out and "EXIT" not in out and not sent, out)


# --- cloud sessions: REST reads, CCR threads ---------------------------
# Claude Code cloud sessions refuse GraphQL with a 403. Threads then come from
# the CCR route, which lists comment ids only; REST fills in the rest.

REST_COMMENTS = [
    {"id": 501, "path": "app/models/user.rb", "line": 51, "in_reply_to_id": None,
     "user": {"login": "revisora-ficticia"}, "body": FINDING_BODY,
     "created_at": "2026-01-02T10:00:00Z", "html_url": "https://example.test/c/501"},
    {"id": 502, "path": "app/models/user.rb", "line": 51, "in_reply_to_id": 501,
     "user": {"login": "autora-ficticia"}, "body": "Ya lo corregí.",
     "created_at": "2026-01-02T11:00:00Z", "html_url": "https://example.test/c/502"},
    {"id": 601, "path": "app/x.rb", "line": None, "in_reply_to_id": None,
     "user": {"login": "otra-cuenta-ficticia"}, "body": "Nombre poco claro.",
     "created_at": "2026-01-01T09:00:00Z", "html_url": "https://example.test/c/601"},
]

CCR_THREADS = [
    {"resolved": False, "outdated": False, "path": "app/models/user.rb",
     "line": 51, "comment_ids": [501, 502]},
    {"resolved": True, "outdated": True, "path": "app/x.rb", "line": None,
     "comment_ids": [601, 999]},
]

GRAPHQL_THREADS = [
    {"id": "PRRT_ficticio1", "isResolved": False, "isOutdated": False,
     "path": "app/models/user.rb", "line": 51,
     "comments": {"nodes": [{"databaseId": 501, "url": "https://example.test/c/501",
                             "author": {"login": "revisora-ficticia"},
                             "body": FINDING_BODY,
                             "createdAt": "2026-01-02T10:00:00Z"}]}},
]


def read_json_out(out):
    return json.loads(out[:out.rindex("}") + 1][out.index("{"):])


def test_threads_from_graphql():
    out = run([], sub="threads", review_threads=GRAPHQL_THREADS,
              comments=REST_COMMENTS, ccr=CCR_THREADS)
    data = read_json_out(out)
    first = data["threads"][0]
    check("threads read through GraphQL keep node ids and known resolution",
          data["source"] == "graphql" and data["resolution"] == "known"
          and first["id"] == "PRRT_ficticio1"
          and first["comments"][0] == {"id": 501, "author": "revisora-ficticia",
                                       "body": FINDING_BODY,
                                       "createdAt": "2026-01-02T10:00:00Z",
                                       "url": "https://example.test/c/501"}, out)


def test_threads_from_ccr_when_graphql_is_refused():
    out = run([], sub="threads", graphql="blocked",
              comments=REST_COMMENTS, ccr=CCR_THREADS)
    data = read_json_out(out)
    live, outdated = data["threads"]
    check("a refused GraphQL takes the CCR route, filled in from REST",
          data["source"] == "ccr" and data["resolution"] == "known"
          and live["id"] == "comment:501" and live["isResolved"] is False
          and [c["author"] for c in live["comments"]]
          == ["revisora-ficticia", "autora-ficticia"]
          and live["comments"][1]["body"] == "Ya lo corregí.", out)
    check("an outdated CCR thread keeps line null and drops an unknown id",
          outdated["line"] is None and outdated["isOutdated"] is True
          and [c["id"] for c in outdated["comments"]] == [601]
          and "[999]" in out and "EXIT" not in out, out)


def test_threads_fall_to_rest_when_ccr_fails():
    out = run([], sub="threads", graphql="blocked", comments=REST_COMMENTS)
    data = read_json_out(out)
    first = data["threads"][0]
    check("CCR failing too falls back to REST with resolution unknown",
          data["source"] == "rest" and data["resolution"] == "unknown"
          and "resolution state unknown" in out
          and first["id"] is None and first["isResolved"] is False
          and [c["id"] for c in first["comments"]] == [501, 502], out)


def test_other_graphql_errors_skip_ccr():
    out = run([], sub="threads", graphql="error",
              comments=REST_COMMENTS, ccr=CCR_THREADS)
    check("a GraphQL failure that is not the session 403 goes straight to REST",
          read_json_out(out)["source"] == "rest", out)


def test_a_ccr_thread_is_resolved_through_ccr():
    sent = []
    out = run(["--resolve", write("t_ccr.json", ["comment:501", "comment:601"])],
              sent=sent, graphql="blocked", comments=REST_COMMENTS, ccr=CCR_THREADS)
    check("a CCR thread of ours is resolved through ccr/comments/<id>/resolve",
          [item for item in sent if "ccr_resolve" in item] == [{"ccr_resolve": "501"}]
          and not any("resolve" in item for item in sent)
          and "resolve=1" in out, out)


def test_pr_and_diff_read_through_rest():
    meta = read_json_out(run([], sub="pr"))
    patch = run([], sub="diff")
    check("pr prints the REST metadata, normalized",
          meta["headSha"] == HEAD and meta["author"] == "autora-ficticia"
          and meta["base"] == "main" and meta["files"] == ["app/models/user.rb"],
          json.dumps(meta))
    check("diff prints the patch from the REST diff media type",
          patch == DIFF, patch)


def main():
    print("post_review.py")
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            test()
    print()
    if failures:
        print(f"{len(failures)} failed: {', '.join(failures)}")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
