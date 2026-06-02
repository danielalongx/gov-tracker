# gov-tracker

Monitors Trump's Truth Social posts and Federal Register presidential documents for investment-relevant signals, pushing ntfy notifications when the LLM rates a post ≥ 6/10 for market impact.

## Architecture

```
gov-tracker/
  collector/           → fetches raw posts/documents, writes to DB only
    truth_social.py    → ScrapeCreators REST API → posts table
    federal_register.py→ Federal Register API   → posts table
  analyzer/
    llm.py             → keyword pre-filter + Claude Haiku → analysis table
  notifier/
    ntfy.py            → reads analysis table, HTTP POST to ntfy.sh
  db/
    schema.py          → CREATE TABLE statements
    init_db.py         → creates DB + default user on first run
  main.py              → orchestrator: collector → analyzer → notifier
  data/                → SQLite file lives here (gitignored)
  .github/workflows/   → GitHub Actions cron every 5 min
```

## Pipeline

```
ScrapeCreators API ──► posts table ──► keyword filter
Federal Register API ─┘               │
                                       ▼ (passes filter)
                               Claude Haiku (haiku-4-5)
                                       │
                               analysis table
                                       │ relevance_score ≥ 6
                                       ▼
                               ntfy.sh push notification
```

## Setup

### Prerequisites

| Dependency | Where to get |
|---|---|
| ScrapeCreators API key | [scrapecreators.com](https://scrapecreators.com) |
| Anthropic API key | [console.anthropic.com](https://console.anthropic.com) |
| ntfy channel name | Pick any unique string — no signup needed |

### Installation

```bash
cd gov-tracker
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Fill in .env with your keys
```

### Local run

```bash
python main.py
```

Logs to stdout. Database is created at `data/gov_tracker.db` on first run.

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `SCRAPECREATORS_API_KEY` | Yes | — | ScrapeCreators API key |
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `NTFY_CHANNEL` | Yes | — | ntfy channel (e.g. `my-gov-signals`) |
| `RELEVANCE_THRESHOLD` | No | `6` | Min score (0–10) to trigger a push |

## GitHub Actions deploy

1. Push this repo to GitHub (this directory is the repo root)
2. **Settings → Secrets → Actions**, add three secrets:
   - `SCRAPECREATORS_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `NTFY_CHANNEL`
3. The workflow at `.github/workflows/poll.yml` runs automatically every 5 minutes

> **GitHub Actions free tier note:** 2,000 min/month free. Every-5-min polling = ~8,640 jobs/month — consider `*/15 * * * *` to stay well within limits.

> **Persistence note:** The SQLite DB is ephemeral on GitHub Actions (each run starts fresh). This means deduplication resets each run, and you may see repeat notifications for older posts. For persistent state, mount an artifact, use GitHub Cache, or migrate to a hosted DB.

## ScrapeCreators endpoint

The collector calls:
```
GET https://api.scrapecreators.com/v1/truthsocial/user/posts
    ?handle=realDonaldTrump&limit=20
Header: x-api-key: <key>
```

If ScrapeCreators updates their API path or auth scheme, adjust `SCRAPECREATORS_BASE` and the `requests.get(...)` call in `collector/truth_social.py`.

## DB schema

```sql
posts(id, source, post_id, content, author, posted_at, fetched_at, processed)
analysis(id, post_id, is_relevant, sentiment, tickers, industries, relevance_score, summary, analyzed_at, notified)
users(id, name, ntfy_channel, risk_profile)
subscriptions(id, user_id, topic)
```

`tickers` and `industries` are stored as JSON arrays.

## API server (for mobile app)

A FastAPI server in `api/` exposes the signal database over HTTP so the Expo mobile app can read real data.

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/signals` | Paginated signal list, most recent first |
| GET | `/signals/{id}` | Single signal by post ID |
| GET | `/health` | DB connectivity check |

`GET /signals` query params: `limit` (default 20), `offset`, `source`, `sentiment` (`bullish`/`bearish`/`neutral`/`mixed`), `min_score` (default 6).

### Run locally

```bash
cd api
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs` once running.

## Phase roadmap

| Phase | Status | Description |
|---|---|---|
| 0 | **Done** | Single-user pipeline, Truth Social + Federal Register, ntfy push |
| 1 | Planned | Multi-user: per-user ntfy channels, topic subscriptions, risk profiles |
| 2 | Planned | Persistent cloud DB, web dashboard, historical backtesting |
