# PriceWatch

![PriceWatch dashboard showing tracked products, retailer prices, availability, and historical price charts](docs/dashboard.png)

PriceWatch is a local-first, agent-assisted market research and price-monitoring platform. An AI agent researches products, verifies live retailer listings, and records structured findings that populate a human-readable dashboard. The application turns repeatable agentic tasks into an auditable workflow instead of leaving results in chat transcripts or one-off scripts.

## What the solution does

- Tracks products, retailer listings, availability, and historical EUR prices.
- Lets an AI agent perform structured research and submit verified discoveries.
- Uses Model Context Protocol (MCP) in the full local deployment to give the agent purpose-built tools for reading application state, testing listings, inspecting pages, and recording results.
- Populates the dashboard from PostgreSQL so agent output becomes durable, queryable application data.
- Requires human review before a discovered product is added to the active watchlist.
- Runs scheduled and on-demand price checks through source-specific scrapers.
- Detects price changes, availability changes, scraper failures, and suspicious cross-source outliers.
- Records bounded activity events for operational visibility and later review.

## Agentic workflow

The agent does not directly edit dashboard files. It works through structured MCP tools or authenticated API operations backed by the same domain services used by the application:

1. Read the current scopes, products, sources, and listings.
2. Search supported retailers for qualifying products or updated listings.
3. Verify the final URL, product identity, live title, price, and stock state.
4. Store research signals or pending discoveries in PostgreSQL.
5. Present the results in the dashboard for human review.
6. Promote approved discoveries into monitored products and listings.
7. Recheck active listings on schedule and append price history.

This approach gives the agent useful autonomy while keeping durable mutations, review status, and evidence visible to the user.

## Architecture

```mermaid
flowchart LR
    H[Human reviewer] --> D[Next.js dashboard]
    AG[AI research agent] --> MCP[MCP tool adapter]
    MCP --> API[FastAPI domain API]
    D -->|same-origin authenticated proxy| API
    API --> DB[(PostgreSQL)]
    API --> Q[Pending discoveries and research signals]
    Q --> D
    API --> SCH[Scheduler]
    SCH --> SCR[Source-specific scrapers]
    MCP --> SCR
    SCR -->|validated public URLs| WEB[Retail websites]
    API --> LOG[Bounded JSONL activity log]
```

This repository contains the application, agent-facing HTTP workflow, security boundaries, and tests. Deployment-specific MCP adapter configuration and private agent instructions are intentionally excluded. In the full local deployment, the MCP adapter exposes the same controlled application capabilities to the agent.

## Main features

### Agent and MCP integration

- Structured tools instead of unrestricted database or filesystem access.
- Current application state is read from PostgreSQL rather than agent memory.
- Live listing verification before a discovery can be recorded.
- Agent confidence is informational; it cannot approve its own discoveries.
- Destructive integration operations are preview-only.
- Research runs expose status, counts, errors, and summaries in the Activity view.

### Price intelligence

- Multiple retailer-specific HTTP and browser scrapers.
- Product and source registry with reusable scraper behavior.
- Historical price series and price-change tracking.
- Stock and availability monitoring.
- Cross-source comparison and outlier checks.
- On-demand and scheduled price-check runs.
- Import/export workflow for external research jobs.

### Human-facing dashboard

- Overview of tracked products and current best prices.
- Product details, listings, and price charts.
- Source health and scraper status.
- Pending discovery approval and rejection.
- Research signals and follow-up watches.
- Run history, errors, and operational activity.
- Responsive desktop and mobile navigation.

### Reliability and security

- Loopback-only API, dashboard, and database services.
- Random local credentials generated during setup.
- Constant-time API-key comparison and authenticated frontend proxy.
- Origin validation for state-changing requests and WebSockets.
- Public-destination and source-host URL allowlisting.
- Blocking of local files, private networks, unsafe ports, and credential-bearing URLs.
- Validation of every redirect and browser navigation.
- Response-size, import-size, collection, recursion, and connection limits.
- Product-identity checks after final-page navigation.
- Replay-safe imports with durable content claims.
- Shared locking for manual and scheduled price checks.
- Structured JSONL logs that encode control characters.
- Fully pinned, hash-locked Python dependencies and an npm lockfile.
- Content Security Policy, anti-framing headers, and loopback-bound Next.js processes.

## Technology

- FastAPI and Pydantic
- PostgreSQL with SQLAlchemy and Alembic
- APScheduler
- Playwright, HTTPX, and retailer-specific scrapers
- Next.js, React, TypeScript, Tailwind CSS, and TanStack Query
- Model Context Protocol for agent tool integration
- Python `unittest`, Node test runner, ESLint, npm audit, and pip-audit

## Run locally

Prerequisites:

- Windows 10 or 11 with Windows PowerShell 5.1 or PowerShell 7
- Python 3.12, including the `py` launcher
- Node.js 20 or newer with npm
- Docker Desktop with Docker Compose

Start Docker Desktop, clone the repository, and run these commands from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

The execution-policy option applies only to the new PowerShell process; it does not change the user's machine policy. Setup generates random local credentials, installs hash-locked Python packages, downloads the pinned Playwright Chromium browser, and installs locked frontend dependencies. Start waits for PostgreSQL, initializes the database, and starts:

- Dashboard: `http://localhost:3000`
- API documentation: `http://localhost:8000/api/docs`

If those ports are already in use, edit the generated `.env` before the first start. Set `POSTGRES_PORT`, `APP_PORT`, and `FRONTEND_PORT` to free loopback ports; the start script propagates them to Docker, FastAPI, Next.js, the API proxy, WebSockets, and the browser security policy.

An Anthropic API key is optional and needed only for the AI-assisted research workflow.

## Test

```powershell
$env:API_KEY = "test-only-api-key-0123456789abcdef"
$env:DATABASE_URL = "postgresql+asyncpg://pricewatch:test-only-password@127.0.0.1:5432/pricewatch"
$env:DATABASE_URL_SYNC = "postgresql://pricewatch:test-only-password@127.0.0.1:5432/pricewatch"
$env:PRICEWATCH_DEBUG = "false"

.\.venv\Scripts\python.exe -m unittest discover -s tests -v

Push-Location frontend
npm test
npm run lint
npm run build
npm audit
Pop-Location
```

Runtime data, credentials, logs, screenshots, build output, virtual environments, and private agent instructions are intentionally excluded from version control.
