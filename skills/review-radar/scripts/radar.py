#!/usr/bin/env python3
"""Deterministic helpers for the review-radar skill. JSON on stdout.

    radar.py since      --config config.yml [--now <iso8601>]
    radar.py candidates --config config.yml [--pr owner/repo#n] [--slack file.json]
    radar.py gate       --config config.yml --pr owner/repo#n --source github|slack
    radar.py my-prs     --config config.yml --since <iso8601> [--now <iso8601>]

GitHub is read over REST only (`gh api`): cloud sessions answer GraphQL with
403. Review threads come from review-changes' `post_review.py threads`, which
already picks GraphQL, CCR, or REST. Standard library only.
"""

import argparse
import datetime as dt
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
POST_REVIEW = HERE.parent.parent / "review-changes" / "scripts" / "post_review.py"

# A run this close after a scheduled slot is that slot's run, even if the
# routine fired late; its window starts at the slot before.
GRACE = dt.timedelta(minutes=30)

# Used when the host has no tz database. Merida has no daylight saving time.
FIXED_OFFSETS = {"America/Merida": -6}

CI_RED = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}
CI_OK = {"success", "neutral", "skipped"}


def fail(message):
    print(f"radar: {message}", file=sys.stderr)
    sys.exit(1)


def show(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


# --- config.yml -------------------------------------------------------------
# A YAML subset: nested maps by indentation, `[a, b]` flow lists (also on the
# line after their key), `- item` block lists, scalars, and `#` comments.


def strip_comment(line):
    quote = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index]
    return line


def scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def flow_list(text, where):
    text = text.strip()
    if not (text.startswith("[") and text.endswith("]")):
        raise ValueError(f"line {where}: expected a [a, b] list, got {text!r}")
    inner = text[1:-1].strip()
    return [scalar(item) for item in inner.split(",")] if inner else []


def parse_yaml(text):
    lines = []
    for number, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ValueError(f"line {number}: indent with spaces, not tabs")
        clean = strip_comment(raw).rstrip()
        if clean.strip():
            lines.append((len(clean) - len(clean.lstrip()), clean.strip(), number))
    if not lines:
        return {}
    value, index = parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValueError(f"line {lines[index][2]}: unexpected indentation")
    return value


def gather_flow(lines, index):
    """A flow list that may span lines: (text, next index)."""
    parts = []
    while index < len(lines):
        parts.append(lines[index][1])
        index += 1
        if parts[-1].endswith("]"):
            return " ".join(parts), index
    raise ValueError(f"line {lines[index - 1][2]}: unclosed [ list")


def parse_block(lines, index, indent):
    if lines[index][1].startswith("- ") or lines[index][1] == "-":
        items = []
        while index < len(lines) and lines[index][0] == indent \
                and lines[index][1].startswith("-"):
            items.append(scalar(lines[index][1][1:]))
            index += 1
        return items, index
    out = {}
    while index < len(lines) and lines[index][0] == indent:
        _, text, number = lines[index]
        key, sep, rest = text.partition(":")
        if not sep or not key.strip():
            raise ValueError(f"line {number}: expected `key: value`, got {text!r}")
        key, rest = key.strip(), rest.strip()
        index += 1
        if rest.startswith("["):
            flow, index = gather_flow(lines, index - 1)
            out[key] = flow_list(flow.partition(":")[2], number)
        elif rest:
            out[key] = scalar(rest)
        elif index < len(lines) and lines[index][0] > indent:
            if lines[index][1].startswith("["):
                flow, index = gather_flow(lines, index)
                out[key] = flow_list(flow, lines[index - 1][2])
            else:
                out[key], index = parse_block(lines, index, lines[index][0])
        else:
            out[key] = None
    return out, index


def load_config(path):
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError as err:
        fail(f"cannot read config {path}: {err}")
    try:
        cfg = parse_yaml(text)
    except ValueError as err:
        fail(f"{path}: {err}")
    for section, key in (("github", "org"), ("github", "me"), ("github", "repos"),
                         ("schedule", "tz"), ("schedule", "days"),
                         ("schedule", "hours"), ("schedule", "minute")):
        if (cfg.get(section) or {}).get(key) in (None, "", []):
            fail(f"{path}: missing {section}.{key}")
    return cfg


# --- time -------------------------------------------------------------------


def zone(name):
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(name)
    except Exception:  # no tz database on the host, or an unknown name
        if name in FIXED_OFFSETS:
            return dt.timezone(dt.timedelta(hours=FIXED_OFFSETS[name]), name)
        fail(f"unknown time zone {name!r} and no tz database to look it up")


def parse_time(text, tz=dt.timezone.utc):
    try:
        value = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        fail(f"not an ISO 8601 time: {text!r}")
    return value if value.tzinfo else value.replace(tzinfo=tz)


def gh_time(text):
    return parse_time(text) if text else None


def slots_before(now, schedule, tz):
    """Scheduled slots at or before `now`, newest first."""
    days, hours = set(schedule["days"]), sorted(schedule["hours"], reverse=True)
    local = now.astimezone(tz)
    for back in range(15):
        day = local.date() - dt.timedelta(days=back)
        if day.isoweekday() not in days:
            continue
        for hour in hours:
            slot = dt.datetime(day.year, day.month, day.day, hour,
                               schedule["minute"], tzinfo=tz)
            if slot <= local:
                yield slot


def compute_since(now, schedule):
    """(since, first_run_of_day, slot of this run or None)."""
    tz = zone(schedule["tz"])
    slots = slots_before(now, schedule, tz)
    latest = next(slots, None)
    if latest is None:
        fail("no scheduled slot in the last two weeks; check schedule.days")
    if now - latest <= GRACE:
        since = next(slots, None) or latest - dt.timedelta(days=1)
        return since, latest.hour == min(schedule["hours"]), latest
    return latest, False, None


def cmd_since(args):
    cfg = load_config(args.config)
    tz = zone(cfg["schedule"]["tz"])
    now = parse_time(args.now, tz) if args.now else dt.datetime.now(dt.timezone.utc)
    since, first, slot = compute_since(now, cfg["schedule"])
    show({"since": since.isoformat(), "first_run_of_day": first,
          "scheduled": slot is not None,
          "now_local": now.astimezone(tz).strftime("%H:%M")})


# --- GitHub over REST -------------------------------------------------------


def gh(args):
    """Run gh and return stdout. Raises RuntimeError with gh's own message."""
    try:
        done = subprocess.run(["gh", *args], capture_output=True, text=True,
                              check=False)
    except FileNotFoundError:
        fail("gh is not installed")
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or f"gh {' '.join(args)} failed")
    return done.stdout


def api(endpoint):
    return json.loads(gh(["api", endpoint]) or "null")


PER_PAGE = 100
MAX_PAGES = 100


def api_pages(endpoint):
    """Every item of a paginated REST list, one `page=N` request at a time.

    Not `gh api --paginate`: GitHub's `Link` header names the repository by
    numeric id (`repositories/<id>/...`), and the cloud proxy refuses those
    paths with 403 from page 2 on. A page shorter than PER_PAGE is the last.
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


def review_threads(full, number):
    """(source, threads) from post_review.py threads."""
    done = subprocess.run([sys.executable, str(POST_REVIEW), "threads",
                           "--repo", full, "--pr", str(number)],
                          capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or "post_review.py threads failed")
    data = json.loads(done.stdout)
    return data.get("source"), data.get("threads") or []


def login(item):
    return (item or {}).get("login") or ""


def is_bot(user):
    return (user or {}).get("type") == "Bot" or login(user).endswith("[bot]")


def label(repo):
    """Short repo name for messages: platform-purchase -> purchase."""
    return repo.rsplit("-", 1)[-1]


PR_REF = re.compile(r"^([\w.-]+)/([\w.-]+)#(\d+)$")


def parse_ref(text):
    match = PR_REF.match(text.strip())
    if not match:
        fail(f"--pr must look like owner/repo#123, got {text!r}")
    return match.group(1), match.group(2), int(match.group(3))


def pr_summary(pr, owner, repo):
    return {"pr": f"{owner}/{repo}#{pr['number']}", "repo": repo,
            "label": label(repo), "number": pr["number"],
            "title": pr.get("title") or "", "author": login(pr.get("user")),
            "url": pr.get("html_url"),
            "head": ((pr.get("head") or {}).get("sha") or "")[:7]}


_post_review = None


def post_review():
    """review-changes' publisher, imported once for its round definition."""
    global _post_review
    if _post_review is None:
        if not POST_REVIEW.is_file():
            fail(f"review-changes is not installed next to review-radar: {POST_REVIEW}")
        spec = importlib.util.spec_from_file_location("post_review", POST_REVIEW)
        _post_review = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_post_review)
    return _post_review


def is_real_review(review):
    """A review that says something: a round in post_review.py's terms
    (a body, or an approval), or a change request.

    Answering on a thread makes GitHub create an empty COMMENTED review; that
    is a reply, not a review.
    """
    return review.get("state") == "CHANGES_REQUESTED" or post_review().is_round(review)


def my_reviews(reviews, me):
    """My real reviews (see is_real_review), oldest first."""
    mine = [r for r in reviews if login(r.get("user")) == me
            and r.get("state") != "PENDING" and r.get("submitted_at")
            and is_real_review(r)]
    return sorted(mine, key=lambda r: r["submitted_at"])


# --- candidates -------------------------------------------------------------


def why_candidate(pr, cfg, owner, repo):
    """The reason this PR asks for my review, or None."""
    gh_cfg = cfg["github"]
    me, teams = gh_cfg["me"], set(gh_cfg.get("request_teams") or [])
    if me in {login(u) for u in pr.get("requested_reviewers") or []}:
        return f"review pedido a {me}"
    for team in pr.get("requested_teams") or []:
        if team.get("slug") in teams:
            return f"review pedido a @{team['slug']}"
    reviews = api_pages(f"repos/{owner}/{repo}/pulls/{pr['number']}/reviews")
    if my_reviews(reviews, me):
        return "ya lo revisé antes (re-review)"
    return None


PR_URL = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")


def slack_refs(path):
    """Slack requests as {owner/repo#n: [who, ...]}, from the agent's JSON file.

    The file is a list of {"pr": "owner/repo#n" or "url": "<PR link>",
    "requested_by": "<name>"}.
    """
    try:
        items = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        fail(f"cannot read --slack {path}: {err}")
    refs = {}
    for item in items if isinstance(items, list) else []:
        match = PR_URL.search(item.get("url") or "")
        ref = f"{match.group(1)}/{match.group(2)}#{match.group(3)}" if match \
            else (item.get("pr") or "").strip()
        if not PR_REF.match(ref):
            continue
        who = refs.setdefault(ref, [])
        if item.get("requested_by") and item["requested_by"] not in who:
            who.append(item["requested_by"])
    return refs


def merge_slack(out, refs, cfg):
    """Fold Slack requests into the GitHub candidates, one entry per PR."""
    by_ref = {c["pr"]: c for c in out["candidates"]}
    for ref, who in refs.items():
        entry = by_ref.get(ref)
        if entry is None:
            owner, repo, number = parse_ref(ref)
            entry = {"pr": ref, "repo": repo, "label": label(repo), "number": number,
                     "why": "pedido en Slack", "sources": []}
            if owner == cfg["github"]["org"] and repo in cfg["github"]["repos"]:
                try:
                    entry.update(pr_summary(api(f"repos/{owner}/{repo}/pulls/{number}"),
                                            owner, repo))
                except RuntimeError as err:
                    out["errors"].append({"pr": ref, "error": str(err)})
            out["candidates"].append(entry)
            by_ref[ref] = entry
        entry["sources"].append("slack")
        entry["requested_by"] = who
    for entry in out["candidates"]:
        # A PR someone asked for in Slack skips the author filter.
        entry["gate_source"] = "slack" if "slack" in entry["sources"] else "github"


def cmd_candidates(args):
    cfg = load_config(args.config)
    out = {"candidates": [], "errors": []}
    collect_github(args, cfg, out)
    for entry in out["candidates"]:
        entry["sources"] = ["github"]
        entry["requested_by"] = []
    merge_slack(out, slack_refs(args.slack) if args.slack else {}, cfg)
    show(out)


def collect_github(args, cfg, out):
    org, me = cfg["github"]["org"], cfg["github"]["me"]
    if args.pr:
        owner, repo, number = parse_ref(args.pr)
        if owner != org or repo not in cfg["github"]["repos"]:
            out["not_candidate"] = {"pr": args.pr, "reason": "repo no configurado"}
            return
        try:
            pr = api(f"repos/{owner}/{repo}/pulls/{number}")
            reason = why_candidate(pr, cfg, owner, repo)
        except RuntimeError as err:
            out["errors"].append({"pr": args.pr, "error": str(err)})
            return
        if reason:
            out["candidates"].append({**pr_summary(pr, owner, repo), "why": reason})
        else:
            out["not_candidate"] = {"pr": args.pr,
                                    "reason": "sin review pedido a mí ni review mío"}
        return
    for repo in cfg["github"]["repos"]:
        try:
            pulls = api_pages(f"repos/{org}/{repo}/pulls?state=open")
        except RuntimeError as err:
            out["errors"].append({"repo": f"{org}/{repo}", "error": str(err)})
            continue
        for pr in pulls:
            if login(pr.get("user")) == me:
                continue  # my own PRs belong to my-prs
            try:
                reason = why_candidate(pr, cfg, org, repo)
            except RuntimeError as err:
                out["errors"].append({"pr": f"{org}/{repo}#{pr['number']}",
                                      "error": str(err)})
                continue
            if reason:
                out["candidates"].append({**pr_summary(pr, org, repo), "why": reason})


# --- gate -------------------------------------------------------------------


def decide(cfg, ref, source):
    """(decision, reason, pr summary or {})."""
    gh_cfg = cfg["github"]
    me = gh_cfg["me"]
    owner, repo, number = parse_ref(ref)
    if owner != gh_cfg["org"] or repo not in gh_cfg["repos"]:
        return "skip", "repo no configurado", {}
    pr = api(f"repos/{owner}/{repo}/pulls/{number}")
    summary = pr_summary(pr, owner, repo)
    if pr.get("merged") or pr.get("merged_at"):
        return "skip", "mergeado", summary
    if pr.get("state") != "open":
        return "skip", "cerrado", summary
    if pr.get("draft"):
        return "skip", "draft", summary
    author = login(pr.get("user"))
    if author == me:
        return "skip", "PR propio", summary
    reviews = api_pages(f"repos/{owner}/{repo}/pulls/{number}/reviews")
    mine = my_reviews(reviews, me)
    if source == "github" and author not in (gh_cfg.get("my_team_authors") or []) \
            and not mine:
        return "skip", "autor fuera de Merchant Services", summary
    if not mine:
        return "review", "primera revisión", summary
    head = (pr.get("head") or {}).get("sha") or ""
    last = mine[-1].get("commit_id") or ""
    if last == head:
        return "skip", f"ya revisado en {head[:7]}", summary
    try:
        compare = api(f"repos/{owner}/{repo}/compare/{last}...{head}")
    except RuntimeError:
        return "review", f"historial reescrito desde {last[:7]}", summary
    commits = (compare or {}).get("commits") or []
    if commits and all(len(c.get("parents") or []) > 1 for c in commits):
        return "skip", "solo merges de la base", summary
    return "review", f"commits nuevos desde {last[:7]}", summary


def cmd_gate(args):
    cfg = load_config(args.config)
    try:
        decision, reason, summary = decide(cfg, args.pr, args.source)
    except RuntimeError as err:
        show({"pr": args.pr, "decision": "error", "reason": str(err)})
        sys.exit(1)
    show({"pr": args.pr, **summary, "decision": decision, "reason": reason,
          "source": args.source})


# --- my-prs -----------------------------------------------------------------


def after(stamp, since):
    moment = gh_time(stamp)
    return moment is not None and moment > since


def group_comments(comments, me, since, group_bots):
    counts, bots = {}, {}
    for comment in comments:
        user = comment.get("user")
        who = login(user)
        if who == me or not after(comment.get("created_at"), since):
            continue
        if is_bot(user) and group_bots:
            bots[who] = bots.get(who, 0) + 1
        else:
            counts[who] = counts.get(who, 0) + 1
    entries = [{"author": who, "count": n, "bot": is_bot({"login": who})}
               for who, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    if bots:
        entries.append({"author": "bots", "logins": sorted(bots),
                        "count": sum(bots.values()), "bot": True})
    return entries


def new_commits(commits, me, since):
    counts = {}
    for item in commits:
        commit = item.get("commit") or {}
        when = (commit.get("committer") or {}).get("date") \
            or (commit.get("author") or {}).get("date")
        who = login(item.get("author")) or (commit.get("author") or {}).get("name") or "?"
        if who == me or not after(when, since):
            continue
        counts[who] = counts.get(who, 0) + 1
    return [{"author": who, "count": n} for who, n in sorted(counts.items())]


def ci_state(owner, repo, sha, since):
    """(state, failed_since): state is failure|pending|success|none."""
    checks = (api(f"repos/{owner}/{repo}/commits/{sha}/check-runs?per_page=100")
              or {}).get("check_runs") or []
    status = api(f"repos/{owner}/{repo}/commits/{sha}/status") or {}
    statuses = status.get("statuses") or []
    red = [c for c in checks if c.get("status") == "completed"
           and c.get("conclusion") in CI_RED]
    red += [s for s in statuses if s.get("state") in ("failure", "error")]
    if red:
        stamps = [c.get("completed_at") or c.get("updated_at") for c in red]
        return "failure", any(after(stamp, since) for stamp in stamps)
    waiting = [c for c in checks if c.get("status") != "completed"
               or c.get("conclusion") not in CI_OK]
    waiting += [s for s in statuses if s.get("state") == "pending"]
    if waiting:
        return "pending", False
    return ("success" if checks or statuses else "none"), False


def latest_verdicts(reviews, me):
    """Each other reviewer's latest APPROVED or CHANGES_REQUESTED."""
    verdicts = {}
    for review in sorted(reviews, key=lambda r: r.get("submitted_at") or ""):
        who = login(review.get("user"))
        if who != me and review.get("state") in ("APPROVED", "CHANGES_REQUESTED",
                                                  "DISMISSED"):
            verdicts[who] = review["state"]
    return verdicts


def draft_since(owner, repo, pr):
    events = api_pages(f"repos/{owner}/{repo}/issues/{pr['number']}/timeline")
    stamps = [e.get("created_at") for e in events
              if e.get("event") == "convert_to_draft" and e.get("created_at")]
    return gh_time(max(stamps)) if stamps else gh_time(pr.get("created_at"))


def open_threads(full, number):
    """{"open": n or None, "unverified": n}: unknown resolution counts apart."""
    source, threads = review_threads(full, number)
    if source == "rest":
        return {"open": None, "unverified": len(threads)}
    return {"open": sum(1 for t in threads if not t.get("isResolved")),
            "unverified": 0}


def one_pr(cfg, owner, repo, listed, since, now):
    me = cfg["github"]["me"]
    opts = cfg.get("my_prs") or {}
    number, full = listed["number"], f"{owner}/{repo}"
    pr = api(f"repos/{full}/pulls/{number}")  # the list omits mergeable_state
    reviews = api_pages(f"repos/{full}/pulls/{number}/reviews")
    others = [r for r in reviews if login(r.get("user")) != me
              and r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED")]
    new_reviews = [{"author": login(r.get("user")), "state": r["state"]}
                   for r in sorted(others, key=lambda r: r.get("submitted_at") or "")
                   if after(r.get("submitted_at"), since)
                   and (r["state"] != "COMMENTED" or (r.get("body") or "").strip())]
    stamp = since.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    comments = api_pages(f"repos/{full}/pulls/{number}/comments?since={stamp}")
    comments += api_pages(f"repos/{full}/issues/{number}/comments?since={stamp}")
    grouped = group_comments(comments, me, since, bool(opts.get("group_bot_comments", True)))
    commits = new_commits(api_pages(f"repos/{full}/pulls/{number}/commits"),
                          me, since)
    head = (pr.get("head") or {}).get("sha") or ""
    ci, failed_now = ci_state(owner, repo, head, since)
    verdicts = latest_verdicts(reviews, me)
    approved = "APPROVED" in verdicts.values()
    blocked = "CHANGES_REQUESTED" in verdicts.values()
    threads = {"open": None, "unverified": 0}
    ready = False
    if approved and not blocked and ci in ("success", "none"):
        threads = open_threads(full, number)
        ready = threads["open"] == 0 or (threads["open"] is None
                                         and threads["unverified"] == 0)
    draft = bool(pr.get("draft"))
    started = draft_since(owner, repo, pr) if draft else None
    updated = gh_time(pr.get("updated_at")) or now
    idle = max(0, (now - updated).days)
    events = {"reviews": new_reviews, "comments": grouped, "commits": commits,
              "ci_failed": {"sha": head[:7]} if failed_now else None}
    return {**pr_summary(pr, owner, repo),
            "has_events": bool(new_reviews or grouped or commits or failed_now),
            "events": events, "ci": ci,
            "conflicts": pr.get("mergeable_state") == "dirty",
            "approved": approved, "changes_requested": blocked,
            "threads": threads, "ready": ready, "draft": draft,
            "draft_days": max(0, (now - started).days) if started else None,
            "idle_days": idle,
            "stale": idle >= int(opts.get("stale_days") or 3),
            "has_reviews": bool(others),
            "needs_review": not draft and not others}


def cmd_my_prs(args):
    cfg = load_config(args.config)
    tz = zone(cfg["schedule"]["tz"])
    since = parse_time(args.since, tz)
    now = parse_time(args.now, tz) if args.now else dt.datetime.now(dt.timezone.utc)
    org, me = cfg["github"]["org"], cfg["github"]["me"]
    out = {"since": since.isoformat(), "prs": [], "errors": []}
    for repo in cfg["github"]["repos"]:
        try:
            pulls = api_pages(f"repos/{org}/{repo}/pulls?state=open")
        except RuntimeError as err:
            out["errors"].append({"repo": f"{org}/{repo}", "error": str(err)})
            continue
        for listed in pulls:
            if login(listed.get("user")) != me:
                continue
            try:
                out["prs"].append(one_pr(cfg, org, repo, listed, since, now))
            except RuntimeError as err:
                out["errors"].append({"pr": f"{org}/{repo}#{listed['number']}",
                                      "error": str(err)})
    show(out)


# --- CLI --------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(prog="radar.py")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("since")
    p.add_argument("--config", required=True)
    p.add_argument("--now")
    p.set_defaults(run=cmd_since)

    p = sub.add_parser("candidates")
    p.add_argument("--config", required=True)
    p.add_argument("--pr", help="owner/repo#n")
    p.add_argument("--slack", help="JSON list of PRs requested in Slack, merged in")
    p.set_defaults(run=cmd_candidates)

    p = sub.add_parser("gate")
    p.add_argument("--config", required=True)
    p.add_argument("--pr", required=True, help="owner/repo#n")
    p.add_argument("--source", required=True, choices=["github", "slack"])
    p.set_defaults(run=cmd_gate)

    p = sub.add_parser("my-prs")
    p.add_argument("--config", required=True)
    p.add_argument("--since", required=True)
    p.add_argument("--now")
    p.set_defaults(run=cmd_my_prs)

    args = parser.parse_args(argv)
    args.run(args)


if __name__ == "__main__":
    main()
