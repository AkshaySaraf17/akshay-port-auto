# 🤖 Automated GitHub Project Generator

Automatically generates **3 portfolio projects per day** across 7 tech domains using Gemini AI, then pushes them directly to your GitHub — fully hands-free via GitHub Actions.

## 📂 Domains Covered (rotating)

| # | Domain |
|---|--------|
| 1 | Artificial Intelligence |
| 2 | Machine Learning |
| 3 | Software Engineering |
| 4 | System Design – HLD (High-Level Design) |
| 5 | System Design – LLD (Low-Level Design) |
| 6 | Data Analytics |
| 7 | Data Engineering |

Each generated project includes a complete **README**, **source code files**, a **CI/Docker config**, and **GitHub topics** — ready to show on your profile.

---

## 🚀 Setup (one-time, ~10 minutes)

### 1. Fork / create this repo
Create a new GitHub repo (e.g. `portfolio-automator`) and push these files into it.

### 2. Get a GitHub Personal Access Token (PAT)
1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Click **Generate new token**
3. Scopes needed: `repo` (full), `workflow`
4. Copy the token — you'll only see it once

### 3. Get your Gemini API key
Sign in at [Google AI Studio](https://aistudio.google.com/) and copy your free API key.

### 4. Add repository secrets
In **your repo → Settings → Secrets and variables → Actions → New repository secret**, add:

| Secret name | Value |
|-------------|-------|
| `GEMINI_API_KEY` | Your Gemini API key |
| `GH_PAT` | Your GitHub PAT from step 2 |
| `MY_GITHUB_USERNAME` | Your GitHub username (optional; defaults to repository owner) |

### 5. Enable Actions write permissions
Go to **repo → Settings → Actions → General → Workflow permissions** and select **"Read and write permissions"**.

### 6. Push and test
```bash
git add .
git commit -m "feat: add project automator"
git push
```
Then go to **Actions → Daily Project Generator → Run workflow** to trigger a manual test run.

---

## ⏰ Schedule
The workflow runs every day at **2:30 AM UTC** / **8:00 AM IST** (edit the cron in `.github/workflows/main.yml` to change the time).

```
0 9 * * *   →  09:00 UTC daily
0 3 * * *   →  03:00 UTC (change to this for 8:30 AM IST)
30 2 * * *  →  02:30 UTC (8:00 AM IST)
```

---

## 🔧 Local usage

```bash
# Install dependency
pip install requests

# Set env vars
export ANTHROPIC_API_KEY="sk-ant-..."
export GITHUB_TOKEN="ghp_..."
export GITHUB_USERNAME="your_username"

# Run
python generate_projects.py
```

---

## 📊 State tracking
`project_state.json` is committed back to this repo after each run. It tracks:
- Every project ever generated (date, title, repo name, category, URL)
- Which category to use next (round-robin)
- Last run date (prevents re-running the same day)

---

## 💡 Customisation tips

| What | Where |
|------|-------|
| Change daily count | `PROJECTS_PER_DAY` in `generate_projects.py` |
| Add/remove categories | `CATEGORIES` list in `generate_projects.py` |
| Make repos private | Set `"private": True` in `create_repo()` |
| Change AI model | `model` param in `ask_claude()` |
| Add languages filter | Extend the Claude prompt in `generate_project_spec()` |

---

## ⚠️ Notes
- Each run makes ~6 API calls to Claude (2 per project). Check your Anthropic usage limits.
- GitHub API rate limit: 5 000 req/hour for authenticated users — well within budget.
- Generated repos are public by default so they show on your profile.
