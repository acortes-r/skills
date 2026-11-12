#!/usr/bin/env python3
"""Tests for scripts/radar.py. No network, no dependencies, no pytest.

    python3 skills/review-radar/tests/test_radar.py

Every test replaces the module's `gh` (and `review_threads`) with stubs, so
nothing reaches GitHub. All logins, repos, and ids are invented. A failure
prints the case that broke and exits non-zero.
"""

import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
RADAR = HERE.parent / "scripts" / "radar.py"


def load_radar():
    spec = importlib.util.spec_from_file_location("radar", RADAR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load_radar()
TMP = pathlib.Path(tempfile.mkdtemp(prefix="radar_tests_"))

CONFIG = """\
github:
  org: acme
  me: yo-ficticio
  repos: [tienda-pagos, tienda-web]
  request_teams: [nucleo]        # pedido al team = pedido a mí
  my_team_authors:
    [colega-uno, colega-dos, yo-ficticio]
slack:
  me: U000FAKE01
  team_groups: [S000FAKE01]
  include_dms: true
  notify_channel: U000FAKE01
schedule:
  tz: America/Merida
  days: [1, 2, 3, 4, 5]
  hours: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
  minute: 7
run:
  mode: dry
  max_reviews_per_run: 3
  lock_minutes: 90
my_prs:
  enabled: true
  stale_days: 3
  daily_digest: true
  group_bot_comments: true
"""
CFG_PATH = TMP / "config.yml"
CFG_PATH.write_text(CONFIG)

HEAD = "f00dfacecafe1234"
OLD = "0ldc0mm1t5678abc"
SINCE = "2026-03-10T09:07:00-06:00"
NOW = "2026-03-10T10:07:30-06:00"

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}\n        {detail}")
        failures.append(name)


def pull(number=7, author="colega-uno", draft=False, state="open", merged=False,
         reviewers=(), teams=(), head=HEAD, **extra):
    data = {"number": number, "title": f"Cambio ficticio {number}",
            "user": {"login": author, "type": "User"}, "draft": draft,
            "state": state, "merged": merged,
            "merged_at": "2026-03-09T12:00:00Z" if merged else None,
            "requested_reviewers": [{"login": r} for r in reviewers],
            "requested_teams": [{"slug": t} for t in teams],
            "head": {"sha": head}, "html_url": f"https://example.test/pull/{number}",
            "created_at": "2026-03-01T15:00:00Z", "updated_at": "2026-03-10T15:30:00Z"}
    data.update(extra)
    return data


def review(author, state="COMMENTED", commit=OLD, at="2026-03-09T18:00:00Z",
           body="Ronda 1 · cambios ficticios"):
    return {"user": {"login": author, "type": "User"}, "state": state,
            "commit_id": commit, "submitted_at": at, "body": body}


def comment(author, at="2026-03-10T15:40:00Z", bot=False):
    return {"user": {"login": author, "type": "Bot" if bot else "User"},
            "created_at": at}


def commit_item(author, at="2026-03-10T15:45:00Z", parents=1):
    return {"author": {"login": author},
            "commit": {"author": {"name": author, "date": at},
                       "committer": {"date": at}},
            "parents": [{"sha": "p"}] * parents}


def run(argv, routes, threads=("graphql", [])):
    """Run main() with gh answering from `routes` (endpoint prefix -> data)."""
    calls = []

    def fake_gh(args):
        assert args[0] == "api", f"only REST api calls allowed: {args!r}"
        assert "graphql" not in args, f"GraphQL is forbidden: {args!r}"
        assert "--paginate" not in args, f"--paginate breaks in the cloud: {args!r}"
        if args[1:3] == ["-X", "GET"]:
            endpoint = args[3]
            fields = dict(args[i + 1].split("=", 1) for i in range(4, len(args))
                          if args[i] == "-f")
            calls.append((endpoint, fields))
            value = routes[endpoint]
            return json.dumps(value(fields) if callable(value) else value)
        endpoint = args[1]
        calls.append(endpoint)
        path = endpoint.split("?", 1)[0]
        if path in routes:
            value = routes[path]
            if isinstance(value, Exception):
                raise value
            return json.dumps(value)
        raise AssertionError(f"unexpected gh call: {endpoint}")

    originals = mod.gh, mod.review_threads
    mod.gh = fake_gh
    mod.review_threads = lambda full, number: threads
    buffer = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buffer):
            try:
                mod.main(argv)
            except SystemExit as exit_signal:
                code = exit_signal.code
    finally:
        mod.gh, mod.review_threads = originals
    text = buffer.getvalue()
    try:
        data = json.loads(text)
    except ValueError:
        data = {"raw": text}
    return data, code, calls


def cfg_args(*rest):
    return [rest[0], "--config", str(CFG_PATH), *rest[1:]]


# --- pagination -------------------------------------------------------------


def test_pages_are_requested_one_by_one():
    full = [pull(n) for n in range(1, mod.PER_PAGE + 1)]
    asked = []

    def fake_gh(args):
        assert "--paginate" not in args, args
        endpoint, _, query = args[1].partition("?")
        params = dict(pair.split("=", 1) for pair in query.split("&"))
        asked.append(params)
        return json.dumps(full if params["page"] == "1" else [pull(500)])

    original, mod.gh = mod.gh, fake_gh
    try:
        items = mod.api_pages("repos/acme/tienda-pagos/pulls?state=open")
    finally:
        mod.gh = original
    check("a full page asks for the next one and a short page ends the list",
          len(items) == mod.PER_PAGE + 1 and items[-1]["number"] == 500
          and [p["page"] for p in asked] == ["1", "2"]
          and all(p["per_page"] == str(mod.PER_PAGE) and p["state"] == "open"
                  for p in asked), asked)


# --- config -----------------------------------------------------------------


def test_config_subset_parses():
    cfg = mod.load_config(str(CFG_PATH))
    check("flow list on the line after its key parses",
          cfg["github"]["my_team_authors"] == ["colega-uno", "colega-dos", "yo-ficticio"],
          cfg["github"])
    check("comments are stripped and scalars typed",
          cfg["github"]["request_teams"] == ["nucleo"]
          and cfg["schedule"]["minute"] == 7 and cfg["my_prs"]["enabled"] is True,
          cfg)


# --- since ------------------------------------------------------------------


def since_at(now):
    data, _, _ = run(cfg_args("since", "--now", now), {})
    return data


def test_since_mid_morning():
    data = since_at("2026-03-10T11:07:20-06:00")  # Tuesday, scheduled run
    check("since mid-morning is the previous slot",
          data["since"] == "2026-03-10T10:07:00-06:00"
          and data["first_run_of_day"] is False, data)


def test_since_first_run_of_day():
    data = since_at("2026-03-10T09:07:05-06:00")
    check("first run of the day reaches back to yesterday's last slot",
          data["since"] == "2026-03-09T18:07:00-06:00"
          and data["first_run_of_day"] is True, data)


def test_since_monday_after_weekend():
    data = since_at("2026-03-16T09:08:00-06:00")  # Monday
    check("Monday 9:07 covers from Friday 18:07",
          data["since"] == "2026-03-13T18:07:00-06:00"
          and data["first_run_of_day"] is True, data)


def test_since_out_of_hours():
    data = since_at("2026-03-10T20:00:00-06:00")
    check("a run at 20:00 starts at the last slot, 18:07, and is no digest run",
          data["since"] == "2026-03-10T18:07:00-06:00"
          and data["first_run_of_day"] is False and data["scheduled"] is False, data)


def test_since_late_trigger_keeps_its_slot():
    data = since_at("2026-03-10T10:25:00-06:00")
    check("a routine that fires 18 minutes late still covers from the slot before",
          data["since"] == "2026-03-10T09:07:00-06:00", data)


def test_since_accepts_utc():
    data = since_at("2026-03-10T16:07:10Z")  # 10:07 in Merida
    check("--now in UTC is converted to the schedule's zone",
          data["since"] == "2026-03-10T09:07:00-06:00", data)


# --- candidates -------------------------------------------------------------


def hit(number, repo="tienda-pagos", author="colega-uno"):
    """A search/issues result for a PR."""
    return {"number": number, "user": {"login": author, "type": "User"},
            "repository_url": f"https://api.example.test/repos/acme/{repo}",
            "pull_request": {}}


def search(requested=(), team=(), reviewed=()):
    """search/issues answering by qualifier, one page each."""
    def answer(fields):
        q = fields["q"]
        items = (requested if "review-requested:yo-ficticio" in q
                 and "team-" not in q else
                 team if "team-review-requested:" in q else
                 reviewed if "reviewed-by:" in q else [])
        return {"total_count": len(items),
                "items": list(items) if fields["page"] == "1" else []}
    return answer


def test_candidates_requested_user_and_team():
    routes = {"search/issues": search(requested=[hit(1), hit(3), hit(4, author="yo-ficticio")],
                                      team=[hit(2)]),
              "repos/acme/tienda-pagos/pulls/1": pull(1, reviewers=["yo-ficticio"]),
              "repos/acme/tienda-pagos/pulls/2": pull(2, teams=["nucleo"]),
              "repos/acme/tienda-pagos/pulls/3": pull(3, teams=["otro-team"]),
              "repos/acme/tienda-pagos/pulls/3/reviews": [review("colega-dos")]}
    data, _, calls = run(cfg_args("candidates"), routes)
    got = {c["number"]: c["why"] for c in data["candidates"]}
    check("requested to me or to a configured team counts; others do not",
          got == {1: "review pedido a yo-ficticio", 2: "review pedido a @nucleo"}, got)
    check("my own PRs are left to my-prs",
          "repos/acme/tienda-pagos/pulls/4" not in calls, calls)
    check("no open PR is listed repo by repo",
          not any(isinstance(c, str) and c.split("?")[0].endswith("/pulls")
                  for c in calls), calls)


def test_candidates_search_queries():
    routes = {"search/issues": search(requested=[hit(1)], reviewed=[hit(1)]),
              "repos/acme/tienda-pagos/pulls/1": pull(1, reviewers=["yo-ficticio"])}
    data, _, calls = run(cfg_args("candidates"), routes)
    queries = [fields["q"] for endpoint, fields in
               (c for c in calls if isinstance(c, tuple))]
    base = "is:pr is:open repo:acme/tienda-pagos repo:acme/tienda-web"
    check("three searches over the configured repos: me, each team, reviewed by me",
          queries == [f"{base} review-requested:yo-ficticio",
                      f"{base} team-review-requested:acme/nucleo",
                      f"{base} reviewed-by:yo-ficticio"], queries)
    check("a PR found by two searches is evaluated once",
          calls.count("repos/acme/tienda-pagos/pulls/1") == 1
          and len(data["candidates"]) == 1, calls)


def test_search_pages_by_hand():
    full = [hit(n) for n in range(1, mod.PER_PAGE + 1)]
    pages = []

    def answer(fields):
        pages.append(fields["page"])
        return {"items": full if fields["page"] == "1" else [hit(900)]}

    routes = {"search/issues": answer}
    for n in list(range(1, mod.PER_PAGE + 1)) + [900]:
        routes[f"repos/acme/tienda-pagos/pulls/{n}"] = pull(n, reviewers=["yo-ficticio"])
    data, _, _ = run(cfg_args("candidates"), routes)
    check("a full search page asks for the next one",
          pages[:2] == ["1", "2"] and len(data["candidates"]) == mod.PER_PAGE + 1,
          pages)


def test_search_respects_rate_limit():
    waits, now = [], [1000.0]
    originals = mod.clock, mod.sleep, list(mod._search_times)
    mod.clock = lambda: now[0]
    mod.sleep = lambda seconds: (waits.append(seconds), now.__setitem__(0, now[0] + seconds))
    mod._search_times[:] = []
    try:
        for _ in range(mod.SEARCH_PER_MINUTE + 1):
            mod.search_throttle()
    finally:
        mod.clock, mod.sleep = originals[0], originals[1]
        mod._search_times[:] = originals[2]
    check("the 31st search in a minute waits for the window to free up",
          len(waits) == 1 and 60 <= waits[0] <= 62, waits)


def test_candidates_re_review():
    routes = {"search/issues": search(reviewed=[hit(5)]),
              "repos/acme/tienda-pagos/pulls/5": pull(5),
              "repos/acme/tienda-pagos/pulls/5/reviews": [review("yo-ficticio")]}
    data, _, _ = run(cfg_args("candidates"), routes)
    check("a PR I reviewed before stays a candidate after GitHub drops me (b)",
          [c["number"] for c in data["candidates"]] == [5]
          and data["candidates"][0]["sources"] == ["github"], data)


def reply(author, commit=OLD, at="2026-03-09T19:00:00Z"):
    """The empty COMMENTED review GitHub creates for a reply on a thread."""
    return review(author, "COMMENTED", commit=commit, at=at, body="")


def test_candidates_thread_reply_is_not_a_review():
    routes = {"search/issues": search(reviewed=[hit(6, author="externo-ficticio")]),
              "repos/acme/tienda-pagos/pulls/6": pull(6, author="externo-ficticio"),
              "repos/acme/tienda-pagos/pulls/6/reviews": [reply("yo-ficticio")]}
    data, _, _ = run(cfg_args("candidates"), routes)
    check("a thread reply on an outside author's PR does not make it a candidate",
          data["candidates"] == [], data)


def test_candidates_single_pr():
    routes = {"repos/acme/tienda-web/pulls/9": pull(9, reviewers=["yo-ficticio"])}
    data, _, calls = run(cfg_args("candidates", "--pr", "acme/tienda-web#9"), routes)
    check("--pr evaluates only that PR",
          [c["pr"] for c in data["candidates"]] == ["acme/tienda-web#9"]
          and calls == ["repos/acme/tienda-web/pulls/9"], calls)
    data, _, _ = run(cfg_args("candidates", "--pr", "acme/otro-repo#3"), {})
    check("--pr on an unconfigured repo is not a candidate",
          data["not_candidate"]["reason"] == "repo no configurado", data)


def test_candidates_dedupe_github_and_slack():
    slack = TMP / "slack.json"
    slack.write_text(json.dumps([
        {"url": "https://github.com/acme/tienda-pagos/pull/1", "requested_by": "Colega Uno"},
        {"pr": "acme/tienda-pagos#1", "requested_by": "Colega Dos"},
        {"url": "https://github.com/acme/tienda-web/pull/12", "requested_by": "Colega Dos"},
    ]))
    routes = {"search/issues": search(requested=[hit(1)]),
              "repos/acme/tienda-pagos/pulls/1": pull(1, reviewers=["yo-ficticio"]),
              "repos/acme/tienda-web/pulls/12": pull(12, author="externo-ficticio")}
    data, _, _ = run(cfg_args("candidates", "--slack", str(slack)), routes)
    by_pr = {c["pr"]: c for c in data["candidates"]}
    both = by_pr.get("acme/tienda-pagos#1", {})
    only = by_pr.get("acme/tienda-web#12", {})
    check("a PR found in GitHub and Slack appears once with both sources",
          len(data["candidates"]) == 2 and both.get("sources") == ["github", "slack"]
          and both.get("requested_by") == ["Colega Uno", "Colega Dos"], data)
    check("a Slack-only PR keeps its requester and gates as slack",
          only.get("sources") == ["slack"] and only.get("gate_source") == "slack"
          and only.get("author") == "externo-ficticio", only)


# --- gate -------------------------------------------------------------------


def gate(routes, pr="acme/tienda-pagos#7", source="github"):
    data, code, calls = run(cfg_args("gate", "--pr", pr, "--source", source), routes)
    return data, calls


def gate_routes(pr_data, reviews=(), compare=None):
    routes = {"repos/acme/tienda-pagos/pulls/7": pr_data,
              "repos/acme/tienda-pagos/pulls/7/reviews": list(reviews)}
    if compare is not None:
        routes[f"repos/acme/tienda-pagos/compare/{OLD}...{HEAD}"] = compare
    return routes


def test_gate_rules_in_order():
    cases = [
        ("repo no configurado", {}, "acme/otro-repo#7", "github"),
        ("mergeado", gate_routes(pull(merged=True, state="closed")), None, "github"),
        ("cerrado", gate_routes(pull(state="closed")), None, "github"),
        ("draft", gate_routes(pull(draft=True)), None, "github"),
        ("PR propio", gate_routes(pull(author="yo-ficticio")), None, "github"),
        ("autor fuera de Merchant Services",
         gate_routes(pull(author="externo-ficticio")), None, "github"),
        (f"ya revisado en {HEAD[:7]}",
         gate_routes(pull(), [review("yo-ficticio", commit=HEAD)]), None, "github"),
        ("solo merges de la base",
         gate_routes(pull(), [review("yo-ficticio")],
                     {"commits": [commit_item("colega-uno", parents=2)] * 2}),
         None, "github"),
    ]
    for reason, routes, pr, source in cases:
        data, _ = gate(routes, pr or "acme/tienda-pagos#7", source)
        check(f"gate skips: {reason}",
              data.get("decision") == "skip" and data.get("reason") == reason, data)


def test_gate_reviews():
    data, _ = gate(gate_routes(pull()))
    check("a teammate's PR I never reviewed gets a first review",
          data["decision"] == "review" and data["reason"] == "primera revisión", data)
    data, _ = gate(gate_routes(pull(), [review("yo-ficticio")],
                               {"commits": [commit_item("colega-uno", parents=2),
                                            commit_item("colega-uno")]}))
    check("a real commit after my last review asks for a re-review",
          data["decision"] == "review"
          and data["reason"] == f"commits nuevos desde {OLD[:7]}", data)


def test_gate_outside_author():
    data, _ = gate(gate_routes(pull(author="externo-ficticio")), source="slack")
    check("Slack requests skip the author filter",
          data["decision"] == "review", data)
    data, _ = gate(gate_routes(pull(author="externo-ficticio"),
                               [review("yo-ficticio")],
                               {"commits": [commit_item("externo-ficticio")]}))
    check("an outside author I already reviewed is re-reviewed (b)",
          data["decision"] == "review", data)


def test_gate_ignores_thread_replies():
    data, _ = gate(gate_routes(pull(author="externo-ficticio"), [reply("yo-ficticio")]))
    check("a thread reply does not count as having reviewed an outside author",
          data["reason"] == "autor fuera de Merchant Services", data)
    data, _ = gate(gate_routes(pull(), [reply("yo-ficticio", commit=HEAD)]))
    check("a teammate's PR with only my thread reply gets a first review",
          data["decision"] == "review" and data["reason"] == "primera revisión", data)
    data, _ = gate(gate_routes(pull(), [review("yo-ficticio", commit=OLD),
                                        reply("yo-ficticio", commit=HEAD)],
                               {"commits": [commit_item("colega-uno")]}))
    check("a reply at the head does not count as reviewing the head",
          data["decision"] == "review"
          and data["reason"] == f"commits nuevos desde {OLD[:7]}", data)
    data, _ = gate(gate_routes(pull(), [review("yo-ficticio", "CHANGES_REQUESTED",
                                               commit=HEAD, body="")]))
    check("a change request with no body is a real review",
          data["reason"] == f"ya revisado en {HEAD[:7]}", data)


def test_gate_uses_latest_review():
    reviews = [review("yo-ficticio", commit=HEAD, at="2026-03-08T10:00:00Z"),
               review("yo-ficticio", commit=OLD, at="2026-03-09T10:00:00Z")]
    data, _ = gate(gate_routes(pull(), reviews,
                               {"commits": [commit_item("colega-uno")]}))
    check("the latest of my reviews decides, not the first",
          data["decision"] == "review", data)


# --- my-prs -----------------------------------------------------------------


def my_routes(pr_data, reviews=(), review_comments=(), issue_comments=(),
              commits=(), checks=None, status=None, timeline=()):
    n = pr_data["number"]
    base = f"repos/acme/tienda-pagos/pulls/{n}"
    sha = pr_data["head"]["sha"]
    return {"repos/acme/tienda-pagos/pulls": [pr_data, pull(99, author="colega-dos")],
            "repos/acme/tienda-web/pulls": [],
            base: pr_data,
            f"{base}/reviews": list(reviews),
            f"{base}/comments": list(review_comments),
            f"repos/acme/tienda-pagos/issues/{n}/comments": list(issue_comments),
            f"{base}/commits": list(commits),
            f"repos/acme/tienda-pagos/commits/{sha}/check-runs":
                {"check_runs": checks if checks is not None else
                 [{"status": "completed", "conclusion": "success",
                   "completed_at": "2026-03-10T15:50:00Z"}]},
            f"repos/acme/tienda-pagos/commits/{sha}/status":
                status or {"state": "pending", "statuses": []},
            f"repos/acme/tienda-pagos/issues/{n}/timeline": list(timeline)}


def my_prs(routes, threads=("graphql", [])):
    data, _, calls = run(cfg_args("my-prs", "--since", SINCE, "--now", NOW),
                         routes, threads)
    return data, calls


def mine(**extra):
    return pull(30, author="yo-ficticio", **extra)


def test_my_prs_only_mine():
    data, _ = my_prs(my_routes(mine()))
    check("only PRs I authored are reported",
          [p["number"] for p in data["prs"]] == [30], data)


def test_my_prs_reviews():
    data, _ = my_prs(my_routes(mine(), reviews=[
        review("colega-uno", "APPROVED", at="2026-03-10T15:20:00Z"),
        review("colega-dos", "CHANGES_REQUESTED", at="2026-03-10T15:25:00Z", body=""),
        review("colega-dos", "COMMENTED", at="2026-03-10T15:26:00Z", body=""),
        review("colega-dos", "APPROVED", at="2026-03-09T10:00:00Z"),
        review("yo-ficticio", "COMMENTED", at="2026-03-10T15:30:00Z", body="gracias")]))
    pr = data["prs"][0]
    check("new reviews by others, with author and state, after since",
          pr["events"]["reviews"] == [
              {"author": "colega-uno", "state": "APPROVED", "reviews": 1, "comments": 0},
              {"author": "colega-dos", "state": "CHANGES_REQUESTED", "reviews": 1,
               "comments": 0}], pr["events"])
    check("a CHANGES_REQUESTED that is still the reviewer's latest blocks",
          pr["changes_requested"] is True and pr["ready"] is False, pr)


def review_events(reviews, review_comments=(), issue_comments=()):
    data, _ = my_prs(my_routes(mine(), reviews=reviews,
                               review_comments=review_comments,
                               issue_comments=issue_comments))
    return data["prs"][0]["events"]


def at(minute):
    return f"2026-03-10T15:{20 + minute:02d}:00Z"  # after SINCE (15:07Z)


def test_my_prs_one_entry_per_reviewer():
    events = review_events([review("colega-uno", "APPROVED", at=at(n)) for n in range(4)])
    check("several reviews by one person are one entry with the count",
          events["reviews"] == [{"author": "colega-uno", "state": "APPROVED",
                                 "reviews": 4, "comments": 0}], events)


def test_my_prs_latest_decisive_state_wins():
    events = review_events([review("colega-uno", "APPROVED", at=at(1)),
                            review("colega-uno", "COMMENTED", at=at(2))])
    check("APPROVED then COMMENTED keeps APPROVED",
          events["reviews"][0]["state"] == "APPROVED"
          and events["reviews"][0]["reviews"] == 2, events)
    events = review_events([review("colega-uno", "APPROVED", at=at(1)),
                            review("colega-uno", "CHANGES_REQUESTED", at=at(2))])
    check("APPROVED then CHANGES_REQUESTED ends as CHANGES_REQUESTED",
          events["reviews"][0]["state"] == "CHANGES_REQUESTED", events)
    events = review_events([review("colega-uno", "COMMENTED", at=at(1)),
                            review("colega-uno", "COMMENTED", at=at(2))])
    check("only COMMENTED reviews leave COMMENTED",
          events["reviews"][0]["state"] == "COMMENTED", events)


def test_my_prs_reviewers_ordered_by_state():
    events = review_events([review("colega-tres", "COMMENTED", at=at(1)),
                            review("colega-dos", "CHANGES_REQUESTED", at=at(2)),
                            review("colega-uno", "APPROVED", at=at(3))])
    check("approvals, then change requests, then comments",
          [e["author"] for e in events["reviews"]]
          == ["colega-uno", "colega-dos", "colega-tres"], events)


def test_my_prs_reviewer_comments_fold_in():
    events = review_events(
        [review("colega-uno", "COMMENTED", at=at(1)),
         review("colega-uno", "COMMENTED", at=at(2))],
        review_comments=[comment("colega-uno"), comment("colega-uno"),
                         comment("colega-dos")],
        issue_comments=[comment("colega-uno"), comment("revisor-ia[bot]")])
    check("a reviewer's comments join their review entry",
          events["reviews"] == [{"author": "colega-uno", "state": "COMMENTED",
                                 "reviews": 2, "comments": 3}], events)
    check("people who only commented, and bots, stay in comments",
          events["comments"] == [
              {"author": "colega-dos", "count": 1, "bot": False},
              {"author": "bots", "logins": ["revisor-ia[bot]"], "count": 1,
               "bot": True}], events)


def bot_review(author, state="COMMENTED", at="2026-03-10T15:21:00Z",
               body="Resumen automático ficticio"):
    data = review(author, state, at=at, body=body)
    data["user"]["type"] = "Bot"
    return data


def test_my_prs_bot_reviews_decide_nothing():
    data, calls = my_prs(my_routes(mine(), reviews=[
        bot_review("revisor-ia[bot]", "APPROVED"),
        bot_review("lint-ficticio", "CHANGES_REQUESTED", at="2026-03-10T15:22:00Z"),
        bot_review("revisor-ia[bot]", at="2026-03-10T15:23:00Z")]))
    pr = data["prs"][0]
    check("a bot's approval or change request is no verdict",
          pr["approved"] is False and pr["changes_requested"] is False
          and pr["ready"] is False, pr)
    check("a PR reviewed only by bots still needs review",
          pr["needs_review"] is True and pr["has_reviews"] is False, pr)
    check("new bot reviews fold into one event entry",
          pr["events"]["reviews"] == [{"author": "bots", "count": 3, "bot": True,
                                       "logins": ["lint-ficticio", "revisor-ia[bot]"]}],
          pr["events"])


def test_my_prs_bot_cannot_block_a_human_approval():
    data, _ = my_prs(my_routes(mine(), reviews=[
        review("colega-uno", "APPROVED", at="2026-03-10T15:20:00Z"),
        bot_review("lint-ficticio", "CHANGES_REQUESTED", at="2026-03-10T15:25:00Z")]),
        threads=("graphql", []))
    pr = data["prs"][0]
    check("a person's approval stands over a bot's change request: ready",
          pr["approved"] is True and pr["changes_requested"] is False
          and pr["ready"] is True, pr)
    check("the person's review stays its own event",
          pr["events"]["reviews"][0] == {"author": "colega-uno", "state": "APPROVED",
                                         "reviews": 1, "comments": 0},
          pr["events"])


def test_my_prs_comments_grouped_and_bots():
    data, _ = my_prs(my_routes(mine(),
        review_comments=[comment("colega-uno"), comment("colega-uno"),
                         comment("yo-ficticio"),
                         comment("colega-uno", at="2026-03-10T14:00:00Z")],
        issue_comments=[comment("colega-uno"), comment("revisor-ia[bot]"),
                        comment("lint-ficticio", bot=True)]))
    entries = data["prs"][0]["events"]["comments"]
    check("comments group by author with counts, mine and old ones ignored",
          entries[0] == {"author": "colega-uno", "count": 3, "bot": False}, entries)
    check("bot comments (type Bot or [bot] login) fold into one entry",
          entries[1] == {"author": "bots", "count": 2, "bot": True,
                         "logins": ["lint-ficticio", "revisor-ia[bot]"]}, entries)


def test_my_prs_commits_by_others():
    data, _ = my_prs(my_routes(mine(), commits=[
        commit_item("colega-dos"), commit_item("colega-dos"),
        commit_item("yo-ficticio"), commit_item("colega-dos", at="2026-03-09T10:00:00Z")]))
    check("new commits by others are counted per author; mine are ignored",
          data["prs"][0]["events"]["commits"] == [{"author": "colega-dos", "count": 2}],
          data["prs"][0]["events"])


def test_my_prs_ci_and_conflicts():
    red = [{"status": "completed", "conclusion": "failure",
            "completed_at": "2026-03-10T15:55:00Z"}]
    data, _ = my_prs(my_routes(mine(mergeable_state="dirty"), checks=red))
    pr = data["prs"][0]
    check("CI that failed after since is an event with the head sha",
          pr["ci"] == "failure" and pr["events"]["ci_failed"] == {"sha": HEAD[:7]}
          and pr["has_events"] is True, pr)
    check("mergeable_state dirty reports conflicts", pr["conflicts"] is True, pr)
    old_red = [{"status": "completed", "conclusion": "failure",
                "completed_at": "2026-03-09T10:00:00Z"}]
    data, _ = my_prs(my_routes(mine(), checks=old_red))
    check("CI that was already red before since is not a new event",
          data["prs"][0]["events"]["ci_failed"] is None, data["prs"][0])
    data, _ = my_prs(my_routes(mine(), status={"state": "failure", "statuses": [
        {"state": "failure", "updated_at": "2026-03-10T15:58:00Z"}]}))
    check("a failing commit status also counts as red CI",
          data["prs"][0]["ci"] == "failure", data["prs"][0])


def test_my_prs_ready_to_merge():
    approved = [review("colega-uno", "APPROVED", at="2026-03-10T15:20:00Z")]
    data, _ = my_prs(my_routes(mine(), reviews=approved),
                     threads=("graphql", [{"isResolved": True}]))
    check("approved, CI green, every thread resolved: ready to merge",
          data["prs"][0]["ready"] is True, data["prs"][0])
    data, _ = my_prs(my_routes(mine(), reviews=approved),
                     threads=("graphql", [{"isResolved": False}]))
    check("an open thread keeps it from ready",
          data["prs"][0]["ready"] is False
          and data["prs"][0]["threads"] == {"open": 1, "unverified": 0}, data["prs"][0])
    data, _ = my_prs(my_routes(mine(), reviews=approved),
                     threads=("rest", [{"isResolved": False}, {"isResolved": False}]))
    check("threads read over REST are unverified and never ready",
          data["prs"][0]["ready"] is False
          and data["prs"][0]["threads"] == {"open": None, "unverified": 2},
          data["prs"][0])
    data, _ = my_prs(my_routes(mine(), reviews=approved), threads=("rest", []))
    check("REST with no threads at all is ready", data["prs"][0]["ready"] is True,
          data["prs"][0])
    pending = [{"status": "in_progress", "conclusion": None}]
    data, calls = my_prs(my_routes(mine(), reviews=approved, checks=pending))
    check("pending CI is not ready and is not reported as red",
          data["prs"][0]["ready"] is False and data["prs"][0]["ci"] == "pending"
          and data["prs"][0]["events"]["ci_failed"] is None, data["prs"][0])


def test_my_prs_drafts_and_stale():
    data, _ = my_prs(my_routes(
        mine(draft=True, updated_at="2026-03-05T12:00:00Z"),
        timeline=[{"event": "convert_to_draft", "created_at": "2026-03-04T12:00:00Z"},
                  {"event": "convert_to_draft", "created_at": "2026-03-06T12:00:00Z"}]))
    pr = data["prs"][0]
    check("draft days count from the latest convert_to_draft",
          pr["draft"] is True and pr["draft_days"] == 4, pr)
    check("days without activity come from updated_at and flag stale",
          pr["idle_days"] == 5 and pr["stale"] is True, pr)
    check("a draft is never listed as waiting for review",
          pr["needs_review"] is False and pr["has_events"] is False, pr)
    data, _ = my_prs(my_routes(mine(created_at="2026-03-08T12:00:00Z")))
    pr = data["prs"][0]
    check("a ready PR with no review at all needs review, and is not stale",
          pr["needs_review"] is True and pr["has_reviews"] is False
          and pr["stale"] is False, pr)


def test_links_are_slack_links():
    check("a PR is written <url|label#n> with the github.com URL",
          mod.slack_link("acme", "tienda-pagos", 7)
          == "<https://github.com/acme/tienda-pagos/pull/7|pagos#7>")
    data, _, _ = run(cfg_args("candidates"), {"search/issues": search(requested=[hit(7)]),
                                              "repos/acme/tienda-pagos/pulls/7":
                                                  pull(7, reviewers=["yo-ficticio"])})
    check("candidates carry the link",
          data["candidates"][0]["link"]
          == "<https://github.com/acme/tienda-pagos/pull/7|pagos#7>", data)
    data, _ = my_prs(my_routes(mine()))
    pr = data["prs"][0]
    check("my-prs carries the link",
          pr["link"] == "<https://github.com/acme/tienda-pagos/pull/30|pagos#30>", pr)
    data, code, _ = run(cfg_args("gate", "--pr", "acme/tienda-pagos#7",
                                 "--source", "github"),
                        {"repos/acme/tienda-pagos/pulls/7": RuntimeError("gh: HTTP 502")})
    check("a gate error still carries the link",
          code == 1 and data["link"] == "<https://github.com/acme/tienda-pagos/pull/7|pagos#7>",
          data)


def test_my_prs_error_does_not_stop_others():
    routes = my_routes(mine())
    routes["repos/acme/tienda-web/pulls"] = RuntimeError("gh: HTTP 502")
    data, _ = my_prs(routes)
    check("a failing repo is recorded and the rest still reported",
          [p["number"] for p in data["prs"]] == [30]
          and data["errors"][0]["repo"] == "acme/tienda-web", data)


# --- lock -------------------------------------------------------------------

LOCK_PR = "acme/tienda-pagos#7"
NOW_EPOCH = mod.parse_time(NOW).timestamp()


def ts(minutes_ago, micro=0):
    return f"{NOW_EPOCH - minutes_ago * 60:.0f}.{micro:06d}"


def lock_line(minutes_ago, thread="T1", sha=HEAD[:7], pr=LOCK_PR, micro=0):
    return {"ts": ts(minutes_ago, micro), "thread": thread,
            "text": f"🔒 revisando pagos#7 @ {sha} [rr:{pr}@{sha}]"}


def result_line(minutes_ago, thread="T1", sha=HEAD[:7], pr=LOCK_PR, mark="✅"):
    return {"ts": ts(minutes_ago), "thread": thread,
            "text": f"{mark} pagos#7 · colega-uno · Ronda 2 ({sha}) · aprobado [rr:{pr}@{sha}]"}


def lock(lines, *extra, sha=HEAD, raw=None):
    path = TMP / "locks.json"
    path.write_text(raw if raw is not None else json.dumps(lines, ensure_ascii=False))
    data, code, calls = run(cfg_args("lock", "--lines", str(path), "--pr", LOCK_PR,
                                     "--sha", sha, "--now", NOW, *extra), {})
    assert not calls, calls
    return data, code


def test_lock_none_goes():
    data, code = lock([])
    check("no lock lines → go, with the token to use",
          code == 0 and data["decision"] == "go"
          and data["token"] == f"[rr:{LOCK_PR}@{HEAD[:7]}]", data)


def test_lock_held_by_another_run():
    data, _ = lock([lock_line(20)])
    check("a live 🔒 from another run → skip",
          data["decision"] == "skip"
          and data["reason"] == "ya en revisión en otra corrida"
          and data["held_by"]["thread"] == "T1", data)


def test_lock_released_by_its_result():
    for mark in ("✅", "💬", "📝", "📭", "⚠️"):
        data, _ = lock([lock_line(20), result_line(5, mark=mark)])
        check(f"a later {mark} result with the same token in the same thread → go",
              data["decision"] == "go", data)


def test_lock_result_in_another_thread_does_not_release():
    data, _ = lock([lock_line(20, thread="T2"), result_line(5, thread="T1")])
    check("a result in another run's thread leaves this 🔒 held",
          data["decision"] == "skip" and data["held_by"]["thread"] == "T2", data)


def test_lock_earlier_result_does_not_release():
    data, _ = lock([result_line(30), lock_line(20)])
    check("a result older than the 🔒 does not release it",
          data["decision"] == "skip", data)


def test_lock_expired_goes():
    data, _ = lock([lock_line(91)])
    check("a 🔒 older than lock_minutes with no result is abandoned → go",
          data["decision"] == "go", data)


def test_lock_other_sha_still_blocks():
    data, _ = lock([lock_line(20, sha="abc1234")], sha="def5678")
    check("the lock is per PR: another sha of the same PR still blocks",
          data["decision"] == "skip" and data["held_by"]["sha"] == "abc1234"
          and data["token"].endswith("@def5678]"), data)


def test_lock_other_pr_goes():
    data, _ = lock([lock_line(20, pr="acme/tienda-pagos#8")])
    check("a 🔒 on another PR does not block", data["decision"] == "go", data)


def test_lock_tie_break_oldest_wins():
    lines = [lock_line(2, thread="T1", micro=100), lock_line(2, thread="T2", micro=200)]
    older, _ = lock(lines, "--mine", ts(2, 100))
    newer, _ = lock(lines, "--mine", ts(2, 200))
    check("two 🔒 on the same PR: the older ts goes, the newer skips",
          older["decision"] == "go" and newer["decision"] == "skip"
          and newer["held_by"]["thread"] == "T1", (older, newer))


def test_lock_expired_does_not_win_tie_break():
    lines = [lock_line(95, thread="T1"), lock_line(2, thread="T2")]
    data, _ = lock(lines, "--mine", ts(2))
    check("an abandoned older 🔒 does not beat a live newer one",
          data["decision"] == "go", data)


def test_lock_mine_does_not_block():
    data, _ = lock([lock_line(1)], "--mine", ts(1))
    check("my own 🔒 (--mine) does not block me", data["decision"] == "go", data)


def test_lock_ignores_lines_without_a_lock_mark():
    token = f"[rr:{LOCK_PR}@{HEAD[:7]}]"
    lines = [{"ts": ts(10), "thread": "T1",
              "text": f"⏭️ pagos#7 · colega-uno · omitido: ya en revisión en otra corrida\n"
                      f"🔍 pagos#7 · revisaría {token}"}]
    data, _ = lock(lines)
    check("⏭️ and other lines never lock", data["decision"] == "go", data)


def test_lock_released_by_losing_run_skip():
    skipped = {"ts": ts(1), "thread": "T2",
               "text": f"⏭️ pagos#7 · colega-uno · omitido: ya en revisión en otra corrida "
                       f"[rr:{LOCK_PR}@{HEAD[:7]}]"}
    lines = [lock_line(3, thread="T1"), result_line(2, thread="T1"),
             lock_line(3, thread="T2", micro=5), skipped]
    data, _ = lock(lines)
    check("the run that lost the tie-break releases its 🔒 with its ⏭️ line",
          data["decision"] == "go", data)


def test_lock_multiline_message():
    lines = [{"ts": ts(10), "thread": "T1",
              "text": "algo antes\n" + lock_line(10)["text"]}]
    data, _ = lock(lines)
    check("a 🔒 on any line of a message counts", data["decision"] == "skip", data)


def test_lock_unreadable_skips():
    data, code = lock(None, raw="{no es json")
    check("unreadable lock lines → skip: candados ilegibles",
          code == 0 and data["decision"] == "skip"
          and data["reason"] == "candados ilegibles", data)


def main():
    print("radar.py")
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
