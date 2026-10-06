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

failures = []


def write(name, data):
    path = TMP / name
    path.write_text(json.dumps(data, ensure_ascii=False))
    return str(path)


def run(argv, comments=None, reviews=None, sent=None):
    """Run main() with a stubbed gh. Returns everything it printed."""
    sent = sent if sent is not None else []

    def fake_gh(args, stdin=None):
        if args[:2] == ["auth", "status"]:
            return ""
        if args[:2] == ["api", "user"]:
            return "revisora-ficticia\n"
        if args[0] == "pr" and args[1] == "diff":
            return DIFF
        if args[0] == "pr" and args[1] == "view":
            return json.dumps({"headRefOid": HEAD})
        if args[0] == "api" and args[1].endswith("/comments"):
            return json.dumps(comments or [])
        if args[0] == "api" and args[1].endswith("/reviews"):
            if stdin is None:
                return json.dumps(reviews or [])
            sent.append(json.loads(stdin))
            return json.dumps({"html_url": "https://example.test/r/1"})
        if args[0] == "api" and args[1].endswith("/replies"):
            sent.append({"reply": json.loads(stdin)})
            return "{}"
        raise AssertionError(f"unexpected gh call: {args!r}")

    original, mod.gh = mod.gh, fake_gh
    sys.argv = ["post_review.py", "--repo", "o/n", "--pr", "1"] + argv
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
    sent = []
    out = run(["--findings", findings, "--dry-run"], comments=existing, sent=sent)
    check("a finding whose code moved lines is not reposted",
          "already posted (1)" in out and not sent, out)


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
          "already posted (1)" in out and not sent, out)


def test_new_reply_is_sent_without_a_review():
    existing = [{"path": "app/models/user.rb", "line": 42, "id": 111,
                 "body": FINDING_BODY, "in_reply_to_id": None}]
    replies = write("r2.json", [{"in_reply_to": 111,
                                 "body": "Stripe reintenta el mismo event.id."}])
    out = run(["--replies", replies, "--dry-run"], comments=existing)
    check("a reply alone creates no review object",
          '"in_reply_to": 111' in out and "replies=1" in out
          and "No review would be created" in out, out)


def test_nothing_to_send():
    out = run(["--findings", write("empty.json", []),
               "--replies", write("empty2.json", [])])
    check("no findings and no replies exits cleanly",
          "no findings and no replies" in out, out)


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
          and sole.get("body") == "1 comentario (1 suggestion). Ninguno bloquea el merge.",
          out)


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


def test_notes_require_approve():
    out = run(["--notes", write("n.json", NOTES)])
    check("--notes without --approve is refused",
          "only meaningful with --approve" in out and "EXIT 1" in out, out)


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
