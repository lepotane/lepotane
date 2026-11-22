#!/usr/bin/env python3
"""
Auto-generates custom SVG project cards and updates README.md
for https://github.com/lepotane (no project count limit).

Rules:
- Non-fork public repositories owned by lepotane or mrc-tuner-studio are included
  (excluding meta/profile/DNS repos: lepotane, lepotane.github.io, mrccorps.is-a.dev, register).
- Forked repositories are ONLY included if @lepotane has authored at least 1 commit
  (across any branch of the fork) OR opened a Pull Request for that repository.
  When a fork qualifies, its card title, description and link are derived from
  @lepotane's PR or latest commit rather than the upstream repo's generic blurb.
"""

import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime

USERNAME = "lepotane"
AUTHOR_EMAILS = {"smtmrc@gmail.com", "lepotane@users.noreply.github.com"}
ORGS = ["mrc-tuner-studio"]

EXCLUDED_REPOS = {
    "lepotane",
    "lepotane.github.io",
    "mrccorps.is-a.dev",
    "register",
}

CUSTOM_LINKS = {
    "mrc-site": "https://lepotane.github.io/mrc-site/",
    "mrc-tuner-studio.github.io": "https://mrc-tuner-studio.github.io/",
}

KNOWN_OVERRIDES = {
    "mrc-tuner-studio.github.io": {
        "tag": "FLAGSHIP // AUTOMOTIVE & AI",
        "badge": "WORKSTATION",
        "title": "MRC Tuner Studio",
        "desc": "AI-assisted ECU calibration and binary ROM editing workstation with map recognition, hex diffing & trilingual manual (TR/EN/ZH).",
        "stack": "Binary Analysis · ECU Maps · AI Assistance · TR/EN/ZH",
        "cta": "LIVE SITE ↗",
        "priority": 100,
    },
    "MRC-Tuner-Studio": {
        "tag": "FLAGSHIP // AUTOMOTIVE & AI",
        "badge": "WORKSTATION",
        "title": "MRC Tuner Studio — Core Engine",
        "desc": "AI-assisted ECU calibration and binary ROM editing workstation with map recognition, hex diffing & trilingual manual (TR/EN/ZH).",
        "stack": "C++ · Binary Analysis · ECU Maps · AI Assistance",
        "cta": "OPEN REPO ↗",
        "priority": 99,
    },
    "mrc-crm-erp-saas-system": {
        "tag": "ENTERPRISE SAAS // DESKTOP SHELL",
        "badge": "FULL-STACK",
        "title": "MRC CRM & ERP SaaS Platform",
        "desc": "Multi-tenant enterprise resource & customer management suite pairing a Laravel + Vue reactive core with a native Tauri desktop runtime.",
        "stack": "PHP / Laravel · Vue.js · Tauri (Rust) · REST API",
        "cta": "OPEN REPO ↗",
        "priority": 90,
    },
    "VAG-ABS-Coding-Calculator": {
        "tag": "AUTOMOTIVE PROTOCOLS // DECODER",
        "badge": "326 RECORDS",
        "title": "VAG ABS / ESP Long-Coding Engine",
        "desc": "Deterministic long-coding decoder and byte synthesizer across 13 VAG brake control module families (MK60EC1, MK100, Bosch 8.2/9.0).",
        "stack": "JavaScript · Bitwise Protocol Synthesis · VIN Matrix",
        "cta": "OPEN REPO ↗",
        "priority": 85,
    },
    "MRC-builds": {
        "tag": "MEDIA ECOSYSTEM // AUTONOMOUS CI",
        "badge": "CLOUDSTREAM",
        "title": "MRC CloudStream Plugin Ecosystem",
        "desc": "High-availability Turkish movie, series & anime plugin repository (.cs3) with automated GitHub Actions build & QA pipelines.",
        "stack": "Kotlin / Gradle · GitHub Actions · Automated QA",
        "cta": "OPEN REPO ↗",
        "priority": 80,
    },
    "mrc-site": {
        "tag": "WEB PORTAL // LIVE DEPLOYMENT",
        "badge": "LIVE SITE",
        "title": "MRC CloudStream Release & Guide Portal",
        "desc": "Official web portal, installation guide and real-time repository announcement site for the MRC CloudStream plugin ecosystem.",
        "stack": "HTML5 / CSS3 · Direct Live Site · GitHub Pages",
        "cta": "VISIT SITE ↗",
        "priority": 78,
    },
    "T-CAN485-CANLogger": {
        "tag": "VEHICLE TELEMETRY // CAN & OBD-II",
        "badge": "SIM271KE ECU",
        "title": "W204 SIM271KE Twincharger CANLogger",
        "desc": "Ultra-detailed CAN / OBD-II data logger for Mercedes W204 C180K 1.6 ML Kompressor cold-start misfire diagnostics on LilyGO T-CAN485.",
        "stack": "C++ · CAN 2.0B / OBD-II · SIM271KE · ESP32",
        "cta": "OPEN REPO ↗",
        "priority": 75,
    },
    "gemini-bypass-permission": {
        "tag": "AI AGENT INFRASTRUCTURE // SAFETY",
        "badge": "AGENT GUARD",
        "title": "Autonomous Agent File-Write Guard",
        "desc": "Transactional file-editing layer for AI coding agents — snapshots every write, validates syntax and rolls back automatically.",
        "stack": "Python · Transactional Rollback · Agent Harness",
        "cta": "OPEN REPO ↗",
        "priority": 72,
    },
}

PALETTES = [
    {"c1": "#a855f7", "c2": "#ec4899", "bg": "#110d22", "pillBg": "#241238", "pillText": "#e879f9"},
    {"c1": "#22d3ee", "c2": "#3b82f6", "bg": "#0a1526", "pillBg": "#0c2a3d", "pillText": "#38bdf8"},
    {"c1": "#f59e0b", "c2": "#ef4444", "bg": "#191118", "pillBg": "#331a12", "pillText": "#fbbf24"},
    {"c1": "#38bdf8", "c2": "#818cf8", "bg": "#0d1426", "pillBg": "#17203d", "pillText": "#93c5fd"},
    {"c1": "#10b981", "c2": "#06b6d4", "bg": "#091b1d", "pillBg": "#0c2e28", "pillText": "#34d399"},
    {"c1": "#f43f5e", "c2": "#a855f7", "bg": "#180f20", "pillBg": "#2f1329", "pillText": "#fb7185"},
]


def fetch_json(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "lepotane-profile-sync",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_user_prs():
    """Returns a dict mapping repo name (lowercased) -> latest PR item by USERNAME."""
    prs_by_repo = {}
    try:
        q = urllib.parse.quote(f"author:{USERNAME} type:pr")
        data = fetch_json(f"https://api.github.com/search/issues?q={q}&sort=updated&per_page=100")
        for item in data.get("items", []):
            repo_url = item.get("repository_url", "")
            repo_name = repo_url.rsplit("/", 1)[-1]
            if repo_name.lower() in EXCLUDED_REPOS:
                continue
            key = repo_name.lower()
            if key not in prs_by_repo:
                prs_by_repo[key] = item
    except Exception as exc:
        print(f"Warning fetching PRs: {exc}")
    return prs_by_repo


def is_authored_by_user(commit_obj: dict) -> bool:
    author = commit_obj.get("author") or {}
    if (author.get("login") or "").lower() == USERNAME.lower():
        return True
    c_author = (commit_obj.get("commit") or {}).get("author") or {}
    name = (c_author.get("name") or "").lower()
    email = (c_author.get("email") or "").lower()
    if name == USERNAME.lower() or email in AUTHOR_EMAILS or USERNAME.lower() in email:
        return True
    return False


def inspect_fork_contribution(repo: dict, prs_by_repo: dict):
    """
    Checks if @lepotane has either a PR or at least 1 commit across any branch of this fork.
    Returns contribution metadata dict if qualified, or None if the fork is untouched.
    """
    name = repo["name"]
    owner = (repo.get("owner") or {}).get("login", USERNAME)
    pr = prs_by_repo.get(name.lower())

    latest_user_commit = None
    latest_branch = None
    try:
        branches = fetch_json(f"https://api.github.com/repos/{owner}/{name}/branches?per_page=100")
        for br in branches:
            br_name = br.get("name")
            sha = (br.get("commit") or {}).get("sha")
            if not sha:
                continue
            c_data = fetch_json(f"https://api.github.com/repos/{owner}/{name}/commits/{sha}")
            if is_authored_by_user(c_data):
                c_date = ((c_data.get("commit") or {}).get("author") or {}).get("date") or ""
                if not latest_user_commit or c_date > latest_user_commit["date"]:
                    msg = ((c_data.get("commit") or {}).get("message") or "").strip()
                    lines = [ln.strip() for ln in msg.splitlines() if ln.strip()]
                    subject = lines[0] if lines else f"Commit {sha[:7]}"
                    body = " ".join(lines[1:]) if len(lines) > 1 else subject
                    latest_user_commit = {
                        "sha": sha[:7],
                        "subject": subject,
                        "body": body,
                        "date": c_date,
                        "url": c_data.get("html_url") or f"{repo['html_url']}/commit/{sha}",
                        "branch": br_name,
                    }
                    latest_branch = br_name
    except Exception as exc:
        print(f"Warning inspecting branches for fork {name}: {exc}")

    if not pr and not latest_user_commit:
        return None

    # Build card metadata directly from PR (preferred) or latest user commit
    lang = repo.get("language") or "C++"
    if pr:
        pr_num = pr.get("number")
        pr_title = (pr.get("title") or "").strip()
        # Strip bracket prefix like "[Engine] " if title is long so it fits cleanly
        short_pr_title = re.sub(r"^\[[^\]]+\]\s*", "", pr_title).strip() or pr_title
        pr_url = pr.get("html_url")
        raw_body = (pr.get("body") or "").strip()
        # Remove "Closes #123" / "Summary" boilerplate from PR body start
        clean_body = re.sub(r"(?i)^(closes|fixes|resolves)\s+#?\d+\s*", "", raw_body).strip()
        clean_body = re.sub(r"[#*`>\[\]]+", "", clean_body)
        clean_body = re.sub(r"(?i)^summary\s*", "", clean_body).strip()
        clean_body = re.sub(r"\s+", " ", clean_body).strip()
        if latest_user_commit and len(clean_body) < 30:
            clean_body = latest_user_commit["body"]
        desc = clean_body if clean_body else pr_title
        return {
            "tag": f"UPSTREAM PR #{pr_num} // {name.upper()}",
            "badge": f"PR #{pr_num}" + (f" · {latest_user_commit['sha']}" if latest_user_commit else ""),
            "title": f"{name} — {short_pr_title}",
            "desc": desc,
            "stack": f"{lang} · Branch: {latest_branch or 'PR'} · Authored by @{USERNAME}",
            "cta": "OPEN PR ↗",
            "url": pr_url,
            "priority": 95,
        }

    # Commit-only contribution on fork
    c = latest_user_commit
    short_subj = re.sub(r"^\[[^\]]+\]\s*", "", c["subject"]).strip() or c["subject"]
    return {
        "tag": f"FORK CONTRIBUTION // {name.upper()}",
        "badge": f"COMMIT {c['sha']}",
        "title": f"{name} — {short_subj}",
        "desc": c["body"],
        "stack": f"{lang} · Branch: {c['branch']} · Commit {c['sha']}",
        "cta": "VIEW COMMIT ↗",
        "url": c["url"],
        "priority": 88,
    }


def fetch_all_repos():
    prs_by_repo = fetch_user_prs()
    repos = []
    seen = set()

    urls = [f"https://api.github.com/users/{USERNAME}/repos?per_page=100&sort=updated"]
    for org in ORGS:
        urls.append(f"https://api.github.com/orgs/{org}/repos?per_page=100&sort=updated")

    for u in urls:
        try:
            items = fetch_json(u)
            for r in items:
                name = r.get("name", "")
                if not name or name in EXCLUDED_REPOS or name.lower() in EXCLUDED_REPOS:
                    continue
                if r.get("private"):
                    continue
                if name in seen:
                    continue

                if r.get("fork"):
                    contrib = inspect_fork_contribution(r, prs_by_repo)
                    if not contrib:
                        print(f"Skipping unmodified fork: {name}")
                        continue
                    r["_fork_contrib"] = contrib

                seen.add(name)
                repos.append(r)
        except Exception as exc:
            print(f"Warning fetching {u}: {exc}")

    def sort_key(r):
        name = r.get("name", "")
        if "_fork_contrib" in r:
            prio = r["_fork_contrib"].get("priority", 88)
        else:
            prio = KNOWN_OVERRIDES.get(name, {}).get("priority", 50)
        stars = r.get("stargazers_count", 0)
        pushed = r.get("pushed_at") or ""
        return (prio, stars, pushed)

    repos.sort(key=sort_key, reverse=True)
    return repos


def wrap_two_lines(text: str, max_chars: int = 66):
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ("Open-source engineering project and developer utility.", "")
    words = text.split(" ")
    line1, line2 = [], []
    for w in words:
        cand = (" ".join(line1 + [w])).strip()
        if len(cand) <= max_chars and not line2:
            line1.append(w)
        else:
            line2.append(w)
    l1 = " ".join(line1)
    l2 = " ".join(line2)
    if len(l2) > max_chars + 6:
        l2 = l2[: max_chars + 3].rstrip() + "..."
    return l1, l2


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def resolve_target_url(repo: dict) -> str:
    if "_fork_contrib" in repo:
        return repo["_fork_contrib"]["url"]
    name = repo["name"]
    if name in CUSTOM_LINKS:
        return CUSTOM_LINKS[name]
    homepage = (repo.get("homepage") or "").strip()
    if homepage and homepage.startswith("http"):
        return homepage
    if repo.get("has_pages") and repo.get("owner", {}).get("login") == USERNAME:
        return f"https://{USERNAME}.github.io/{name}/"
    return repo["html_url"]


def build_card_svg(repo: dict, idx: int) -> str:
    name = repo["name"]
    pal = PALETTES[idx % len(PALETTES)]
    ov = repo.get("_fork_contrib") or KNOWN_OVERRIDES.get(name, {})

    lang = repo.get("language") or "Software"
    stars = repo.get("stargazers_count", 0)
    updated_raw = repo.get("pushed_at") or ""
    updated_str = ""
    if updated_raw:
        try:
            dt = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            updated_str = dt.strftime("%b %Y").upper()
        except Exception:
            updated_str = ""

    tag = ov.get("tag") or f"{lang.upper()} // OPEN SOURCE SYSTEM"
    if "badge" in ov:
        badge = ov["badge"]
        if stars > 0 and "STAR" not in badge and name == "MRC-builds":
            badge = f"{stars} STARS · LIVE"
    else:
        badge = f"★ {stars} · {updated_str}" if stars > 0 else (updated_str or lang.upper())

    title = ov.get("title") or name.replace("-", " ").replace("_", " ")
    if len(title) > 42:
        title = title[:40].rstrip() + "…"

    desc = ov.get("desc") or repo.get("description") or f"{name} — open-source {lang} repository."
    line1, line2 = wrap_two_lines(desc, 66)

    topics = repo.get("topics") or []
    if "stack" in ov:
        stack = ov["stack"]
    elif topics:
        stack = " · ".join([lang] + [t for t in topics[:3]])
    else:
        stack = f"{lang} · GitHub Repository · Open Source"

    if len(stack) > 64:
        stack = stack[:62].rstrip() + "…"

    target_url = resolve_target_url(repo)
    if "cta" in ov:
        cta = ov["cta"]
    elif target_url != repo.get("html_url"):
        cta = "LIVE SITE ↗"
    else:
        cta = "OPEN ↗"

    esc = lambda s: html.escape(str(s), quote=True)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 580 190" width="580" height="190" role="img" aria-label="{esc(title)}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{pal['c1']}"/>
      <stop offset="1" stop-color="{pal['c2']}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.9" cy="0.1" r="0.6">
      <stop offset="0" stop-color="{pal['c1']}" stop-opacity="0.18"/>
      <stop offset="1" stop-color="{pal['c1']}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="580" height="190" rx="14" fill="{pal['bg']}"/>
  <rect width="580" height="190" rx="14" fill="url(#glow)"/>
  <rect x="0.75" y="0.75" width="578.5" height="188.5" rx="13.25" fill="none" stroke="#1e293b" stroke-width="1.5"/>
  <rect x="0" y="0" width="580" height="4" rx="2" fill="url(#g)"/>
  <rect x="0" y="28" width="3.5" height="134" rx="1.75" fill="url(#g)"/>
  <text x="24" y="34" fill="{pal['pillText']}" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="10.5" font-weight="700" letter-spacing="1.6">{esc(tag)}</text>
  <rect x="436" y="17" width="122" height="22" rx="6" fill="{pal['pillBg']}" stroke="{pal['c1']}" stroke-opacity="0.45" stroke-width="1"/>
  <text x="497" y="32" text-anchor="middle" fill="{pal['pillText']}" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="10" font-weight="700" letter-spacing="0.9">{esc(badge)}</text>
  <text x="24" y="68" fill="#f8fafc" font-family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="18.5" font-weight="700" letter-spacing="-0.2">{esc(title)}</text>
  <text x="24" y="96" fill="#94a3b8" font-family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="12.3">{esc(line1)}</text>
  <text x="24" y="116" fill="#94a3b8" font-family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="12.3">{esc(line2)}</text>
  <line x1="24" y1="142" x2="556" y2="142" stroke="#1e293b" stroke-width="1"/>
  <text x="24" y="166" fill="#cbd5e1" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="10.8" font-weight="500">{esc(stack)}</text>
  <text x="556" y="166" text-anchor="end" fill="{pal['pillText']}" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="10.8" font-weight="700">{esc(cta)}</text>
</svg>
"""


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cards_dir = os.path.join(root, "assets", "cards")
    os.makedirs(cards_dir, exist_ok=True)

    repos = fetch_all_repos()
    if not repos:
        print("No repositories fetched; aborting to preserve existing README.")
        return

    active_files = set()
    cells = []

    for idx, repo in enumerate(repos):
        slug = slugify(repo["name"])
        filename = f"card-{slug}.svg"
        active_files.add(filename)
        svg_path = os.path.join(cards_dir, filename)
        svg_content = build_card_svg(repo, idx)
        with open(svg_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(svg_content)

        target_url = resolve_target_url(repo)
        ov = repo.get("_fork_contrib") or KNOWN_OVERRIDES.get(repo["name"], {})
        title = ov.get("title") or repo["name"]
        alt = html.escape(title, quote=True)
        cells.append(
            f'    <td width="50%" align="center">\n'
            f'      <a href="{html.escape(target_url, quote=True)}">\n'
            f'        <img src="assets/cards/{filename}" alt="{alt}" width="100%" />\n'
            f'      </a>\n'
            f'    </td>'
        )

    for existing in os.listdir(cards_dir):
        if existing.endswith(".svg") and existing not in active_files:
            os.remove(os.path.join(cards_dir, existing))

    rows = []
    for i in range(0, len(cells), 2):
        if i + 1 < len(cells):
            rows.append("  <tr>\n" + cells[i] + "\n" + cells[i + 1] + "\n  </tr>")
        else:
            rows.append("  <tr>\n" + cells[i] + '\n    <td width="50%"></td>\n  </tr>')

    table_html = "<table>\n" + "\n".join(rows) + "\n</table>"

    readme_path = os.path.join(root, "README.md")
    with open(readme_path, "r", encoding="utf-8") as f:
        readme = f.read()

    pattern = re.compile(r"<!-- PROJECTS:START -->.*?<!-- PROJECTS:END -->", re.DOTALL)
    replacement = f"<!-- PROJECTS:START -->\n{table_html}\n<!-- PROJECTS:END -->"

    if pattern.search(readme):
        new_readme = pattern.sub(replacement, readme)
    else:
        raise RuntimeError("Markers <!-- PROJECTS:START --> / <!-- PROJECTS:END --> not found in README.md")

    with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_readme)

    print(f"Synced {len(repos)} repositories into README.md and assets/cards/.")


if __name__ == "__main__":
    main()
