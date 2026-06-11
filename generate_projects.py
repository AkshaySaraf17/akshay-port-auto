#!/usr/bin/env python3
"""
Automated GitHub Project Generator — FREE VERSION
Uses Google Gemini API (free tier, no credit card) + GitHub API.
Generates 3 portfolio projects per day across 7 tech domains.
"""

import os
import sys
import json
import time
import base64
import logging
import requests
from datetime import datetime
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN    = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or ""
GITHUB_USERNAME = os.environ.get("MY_GITHUB_USERNAME") or os.environ.get("GITHUB_USERNAME") or ""

PROJECTS_PER_DAY = 3
STATE_FILE       = Path("project_state.json")
LOG_FILE         = Path("generator.log")

CATEGORIES = [
    "Artificial Intelligence",
    "Machine Learning",
    "Software Engineering",
    "System Design - HLD (High-Level Design)",
    "System Design - LLD (Low-Level Design)",
    "Data Analytics",
    "Data Engineering",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


# ── State helpers ───────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"generated": [], "last_run": None, "category_index": 0}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Gemini API (FREE, no credit card) ──────────────────────────────────────
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash-preview-05-20:generateContent"
)

def ask_gemini(prompt: str) -> str:
    """Call Gemini 2.5 Flash — completely free, 1500 req/day limit."""
    params = {"key": GEMINI_API_KEY}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.7},
    }
    for attempt in range(3):
        resp = requests.post(GEMINI_URL, params=params, json=body, timeout=120)
        if resp.status_code == 429:
            wait = 60 * (attempt + 1)
            log.warning(f"  Rate limited — waiting {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    raise RuntimeError("Gemini API rate limit exceeded after retries.")


def generate_project_spec(category: str, existing_titles: list) -> dict:
    avoid = ", ".join(existing_titles[-30:]) if existing_titles else "none"
    prompt = f"""You are a senior engineer creating a portfolio project for: {category}.

Already generated (avoid duplicates): {avoid}

Return ONLY valid JSON — no markdown fences, no preamble, no explanation.

{{
  "repo_name": "kebab-case-name",
  "title": "Human Readable Title",
  "description": "One-line description under 120 chars",
  "tech_stack": ["tech1", "tech2", "tech3"],
  "readme": "<complete README.md in markdown>",
  "files": [
    {{"path": "src/main.py", "content": "# real code here"}},
    {{"path": "tests/test_main.py", "content": "# real tests here"}}
  ]
}}

Requirements:
- repo_name: lowercase, hyphens only
- README must have: Overview, Architecture, Tech Stack, Setup, Usage, Contributing
- Include 4-6 real source files (logic + tests + Dockerfile or CI)
- Write real working starter code — not just comments or stubs
- The category "{category}" must be clearly reflected in the project
- Return the JSON object ONLY"""

    raw = ask_gemini(prompt).strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw.strip())


# ── GitHub API ──────────────────────────────────────────────────────────────
def gh_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}


def unique_repo_name(base: str) -> str:
    """Always returns a unique repo name by appending YYYYMMDD + 4-char random suffix."""
    import random, string
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    date_str = datetime.now().strftime("%Y%m%d")
    return f"{base}-{date_str}-{suffix}"


def create_repo(name: str, description: str) -> bool:
    body = {"name": name, "description": description, "private": False, "auto_init": False}
    r = requests.post("https://api.github.com/user/repos", headers=gh_headers(), json=body)
    if r.status_code == 201:
        log.info(f"  ✅ Repo created: {name}")
        return True
    log.error(f"  ❌ Failed: {r.status_code} — {r.text[:200]}")
    return False


def push_file(repo: str, path: str, content: str, message: str):
    encoded = base64.b64encode(content.encode()).decode()
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo}/contents/{path}"
    existing = requests.get(url, headers=gh_headers())
    body = {"message": message, "content": encoded}
    if existing.status_code == 200:
        body["sha"] = existing.json()["sha"]
    r = requests.put(url, headers=gh_headers(), json=body)
    if r.status_code not in (200, 201):
        log.warning(f"    ⚠️  {path}: {r.status_code}")


def set_topics(repo: str, topics: list):
    clean = [t.lower().replace(" ", "-").replace("(","").replace(")","") for t in topics][:20]
    requests.put(
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo}/topics",
        headers={**gh_headers(), "Accept": "application/vnd.github.mercy-preview+json"},
        json={"names": clean},
    )


def upload_project(spec: dict, category: str):
    # Generate a guaranteed-unique name — a fresh repo is ALWAYS created
    name = unique_repo_name(spec["repo_name"])
    log.info(f"  📁 New repo name: {name}")

    if not create_repo(name, spec["description"]):
        return None
    time.sleep(2)   # give GitHub a moment to initialise

    push_file(name, "README.md", spec["readme"], "docs: add README")
    for f in spec.get("files", []):
        push_file(name, f["path"], f["content"], f"feat: add {f['path']}")
        time.sleep(0.4)

    topics = spec.get("tech_stack", []) + [category.split()[0].lower(), "portfolio"]
    set_topics(name, topics)

    url = f"https://github.com/{GITHUB_USERNAME}/{name}"
    log.info(f"  🚀 Live: {url}")
    return url


# ── Daily runner ────────────────────────────────────────────────────────────
def run_daily():
    if not all([GEMINI_API_KEY, GITHUB_TOKEN, GITHUB_USERNAME]):
        log.error(
            "Set these environment variables:\n"
            "  GEMINI_API_KEY  → https://aistudio.google.com/app/apikey (free)\n"
            "  GITHUB_TOKEN    → GitHub > Settings > Developer settings > PAT\n"
            "  GITHUB_USERNAME → your GitHub username"
        )
        sys.exit(1)

    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = sum(1 for p in state["generated"] if p.get("date") == today)

    if today_count >= PROJECTS_PER_DAY:
        log.info(f"Already generated {PROJECTS_PER_DAY} projects today. Done.")
        return

    existing_titles = [p["title"] for p in state["generated"]]
    cat_idx = state.get("category_index", 0)
    to_generate = PROJECTS_PER_DAY - today_count

    log.info(f"📅 {today} — Generating {to_generate} project(s)...")

    for i in range(to_generate):
        category = CATEGORIES[cat_idx % len(CATEGORIES)]
        cat_idx += 1
        log.info(f"\n[{i+1}/{to_generate}] Category: {category}")
        try:
            spec = generate_project_spec(category, existing_titles)
            log.info(f"  📦 {spec['title']} ({spec['repo_name']})")
            url = upload_project(spec, category)
            if url:
                state["generated"].append({
                    "date": today, "title": spec["title"],
                    "repo": spec["repo_name"], "category": category, "url": url,
                })
                existing_titles.append(spec["title"])
        except Exception as e:
            log.error(f"  ❌ Failed: {e}")
        time.sleep(10)

    state["last_run"] = today
    state["category_index"] = cat_idx
    save_state(state)
    log.info("\n✅ Done for today!")


if __name__ == "__main__":
    run_daily()
