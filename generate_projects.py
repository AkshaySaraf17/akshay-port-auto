#!/usr/bin/env python3
"""
Automated GitHub Project Generator
Generates 3 projects daily across AI, ML, Software Engineering, System Design,
LLD, HLD, Data Analytics, and Data Engineering domains using Claude AI.
"""

import os
import json
import time
import base64
import random
import logging
import requests
from datetime import datetime
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USERNAME   = os.environ.get("GITHUB_USERNAME", "")

PROJECTS_PER_DAY  = 3
STATE_FILE        = Path("project_state.json")
LOG_FILE          = Path("generator.log")

CATEGORIES = [
    "AI",
    "Machine Learning",
    "Software Engineering",
    "System Design - HLD",
    "System Design - LLD",
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


# ── Claude API ──────────────────────────────────────────────────────────────
def ask_claude(prompt: str, system: str = "") -> str:
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=120)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def generate_project_spec(category: str, existing_titles: list[str]) -> dict:
    """Ask Claude to design a complete project for a given category."""
    avoid = ", ".join(existing_titles[-30:]) if existing_titles else "none"
    prompt = f"""
You are a senior engineer creating a portfolio project for the category: **{category}**.

Already generated (avoid duplicates): {avoid}

Return ONLY valid JSON (no markdown fences) with exactly these keys:
{{
  "repo_name": "kebab-case-name",
  "title": "Human Readable Title",
  "description": "One-line description (max 120 chars)",
  "tech_stack": ["tech1", "tech2"],
  "readme": "<full README.md content in markdown>",
  "files": [
    {{"path": "relative/path.ext", "content": "file content here"}}
  ]
}}

Requirements:
- repo_name: lowercase, hyphens only, no spaces
- README must have: Overview, Architecture, Tech Stack, Setup, Usage, Contributing sections
- Include 3-6 meaningful source files (main logic, config, tests, docker/ci if relevant)
- Files should contain real, working starter code (not just stubs)
- Category "{category}" must be clearly reflected in the project purpose
"""
    raw = ask_claude(prompt)
    # Strip accidental markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw.strip())


# ── GitHub API ──────────────────────────────────────────────────────────────
GH_HEADERS = lambda: {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}


def repo_exists(name: str) -> bool:
    r = requests.get(f"https://api.github.com/repos/{GITHUB_USERNAME}/{name}", headers=GH_HEADERS())
    return r.status_code == 200


def create_repo(name: str, description: str) -> bool:
    body = {
        "name": name,
        "description": description,
        "private": False,
        "auto_init": False,
    }
    r = requests.post("https://api.github.com/user/repos", headers=GH_HEADERS(), json=body)
    if r.status_code == 201:
        log.info(f"  ✅ Created repo: {name}")
        return True
    log.error(f"  ❌ Failed to create repo {name}: {r.status_code} {r.text[:200]}")
    return False


def push_file(repo: str, path: str, content: str, message: str):
    encoded = base64.b64encode(content.encode()).decode()
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo}/contents/{path}"
    # Check if file already exists (get its sha)
    existing = requests.get(url, headers=GH_HEADERS())
    body = {"message": message, "content": encoded}
    if existing.status_code == 200:
        body["sha"] = existing.json()["sha"]
    r = requests.put(url, headers=GH_HEADERS(), json=body)
    if r.status_code not in (200, 201):
        log.warning(f"    ⚠️  Could not push {path}: {r.status_code}")


def set_topics(repo: str, topics: list[str]):
    requests.put(
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo}/topics",
        headers={**GH_HEADERS(), "Accept": "application/vnd.github.mercy-preview+json"},
        json={"names": [t.lower().replace(" ", "-") for t in topics][:20]},
    )


def upload_project(spec: dict, category: str) -> str | None:
    name = spec["repo_name"]
    if repo_exists(name):
        name = f"{name}-{datetime.now().strftime('%Y%m')}"
    if not create_repo(name, spec["description"]):
        return None

    time.sleep(2)  # let GitHub initialise the repo

    # Push README first
    push_file(name, "README.md", spec["readme"], "docs: add README")

    # Push all generated files
    for f in spec.get("files", []):
        push_file(name, f["path"], f["content"], f"feat: add {f['path']}")
        time.sleep(0.3)

    # Tag with topics
    topics = spec.get("tech_stack", []) + [category.split()[0].lower(), "portfolio", "automated"]
    set_topics(name, topics)

    url = f"https://github.com/{GITHUB_USERNAME}/{name}"
    log.info(f"  🚀 Uploaded: {url}")
    return url


# ── Daily runner ────────────────────────────────────────────────────────────
def run_daily():
    if not all([ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_USERNAME]):
        log.error("Missing environment variables: ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_USERNAME")
        return

    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    # Count how many already generated today
    today_count = sum(1 for p in state["generated"] if p.get("date") == today)
    if today_count >= PROJECTS_PER_DAY:
        log.info(f"Already generated {PROJECTS_PER_DAY} projects today ({today}). Nothing to do.")
        return

    existing_titles = [p["title"] for p in state["generated"]]
    cat_idx = state.get("category_index", 0)

    to_generate = PROJECTS_PER_DAY - today_count
    log.info(f"📅 {today} — Generating {to_generate} project(s)…")

    for i in range(to_generate):
        category = CATEGORIES[cat_idx % len(CATEGORIES)]
        cat_idx += 1
        log.info(f"\n[{i+1}/{to_generate}] Category: {category}")

        try:
            spec = generate_project_spec(category, existing_titles)
            log.info(f"  📦 Project: {spec['title']} ({spec['repo_name']})")
            url = upload_project(spec, category)
            if url:
                state["generated"].append({
                    "date": today,
                    "title": spec["title"],
                    "repo": spec["repo_name"],
                    "category": category,
                    "url": url,
                })
                existing_titles.append(spec["title"])
        except Exception as e:
            log.error(f"  ❌ Failed for {category}: {e}")

        time.sleep(5)  # rate-limit buffer

    state["last_run"] = today
    state["category_index"] = cat_idx
    save_state(state)
    log.info("\n✅ Done for today!")


if __name__ == "__main__":
    run_daily()
