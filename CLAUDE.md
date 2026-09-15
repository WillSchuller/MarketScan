# CLAUDE.md

## Project Overview

This project is a minimal sports-market data scanner written in Python.

Its current purpose is to:

1. Retrieve sportsbook odds from SportsGameOdds.
2. Retrieve prediction-market data from Kalshi.
3. Include only sporting events that:

   * have NOT started;
   * are scheduled to start on the same local calendar day as the request;
   * currently have sportsbook odds available.
4. Normalize the returned data into a small internal representation that can later support:

   * market matching;
   * de-vigging;
   * consensus probability calculations;
   * expected-value calculations;
   * alerts;
   * optional automated trading.

Those later features are NOT part of the current implementation unless explicitly requested.

The current application is read-only.

---

# Core Development Philosophy

## Keep the code minimal

Always implement the smallest correct solution.

Prefer:

* simple functions;
* small modules;
* Python standard library where practical;
* direct API calls;
* explicit data transformations;
* obvious control flow;
* a small number of dependencies.

Avoid:

* unnecessary classes;
* dependency injection frameworks;
* factory patterns;
* repositories/services/controllers unless genuinely needed;
* premature abstractions;
* generic plugin systems;
* speculative scalability work;
* unnecessary async code;
* unnecessary databases;
* unnecessary caching;
* frontend work;
* duplicated API models;
* excessive configuration.

Do not write code for possible future requirements unless the user explicitly requests them.

If a feature can be implemented clearly in 20 lines, do not create 100 lines of architecture around it.

---

# Scope Lock

The current implementation should do only this:

```text
Current local date/time
        |
        v
Determine start/end of today's local calendar day
        |
        v
Convert boundaries to UTC
        |
        v
SportsGameOdds API
        |
        |-- only events starting today
        |-- started = false
        |-- oddsAvailable = true
        |
        v
Today's upcoming sporting events
        |
        v
Kalshi open markets
        |
        v
Retain potentially relevant sports/player markets
        |
        v
Normalized read-only output
```

DO NOT implement:

* automatic Kalshi trading;
* order submission;
* bankroll management;
* Kelly sizing;
* EV-based trade execution;
* sportsbook scraping;
* browser automation;
* historical modeling;
* machine learning;
* live/in-play betting;
* games that have already started;
* games scheduled for tomorrow;
* games from earlier today;
* persistent background services;
* polling loops unless explicitly requested.

---

# Language and Runtime

Use:

```text
Python 3.11+
```

Prefer Python 3.12 if starting a new environment.

Use type hints for public functions.

Do not require advanced typing patterns.

---

# Preferred Dependencies

Use as few dependencies as possible.

Current preferred dependencies:

```text
httpx
python-dotenv
```

Testing:

```text
pytest
```

Do not add pandas unless tabular analysis genuinely requires it.

Do not add SQLAlchemy.

Do not add FastAPI.

Do not add Pydantic unless validation complexity justifies it.

Do not add an ORM.

---

# Suggested Minimal Repository Structure

Prefer:

```text
project/
|
|-- CLAUDE.md
|-- README.md
|-- requirements.txt
|-- .gitignore
|-- .env.example
|
|-- src/
|   |-- main.py
|   |-- config.py
|   |-- time_utils.py
|   |-- sports_odds.py
|   |-- kalshi.py
|   `-- models.py
|
`-- tests/
    |-- test_time_utils.py
    |-- test_sports_odds.py
    `-- test_kalshi.py
```

Do not add additional files unless they serve an immediate purpose.

If the project is still extremely small, combining modules is acceptable.

For example:

```text
src/
|-- main.py
|-- sports_odds.py
`-- kalshi.py
```

is preferable to excessive fragmentation.

---

# Secrets and Credentials

## Absolute rule

NEVER:

* hard-code API keys;
* print API keys;
* log API keys;
* commit API keys;
* place private keys in source code;
* place secrets in test fixtures;
* put real credentials in README files;
* include secrets in exception messages.

All credentials must come from environment variables or ignored secret files.

---

# Environment Variables

Use:

```text
SPORTS_GAME_ODDS_API_KEY=

APP_TIMEZONE=America/Chicago

KALSHI_ENVIRONMENT=production
```

For the current read-only implementation, Kalshi public market-data endpoints do not require API credentials.

If authenticated Kalshi functionality is added later, use:

```text
KALSHI_API_KEY_ID=
KALSHI_PRIVATE_KEY_PATH=
```

Never place the private-key contents directly in `.env`.

Store the private key as a local ignored file and reference its path.

Example:

```text
KALSHI_PRIVATE_KEY_PATH=./secrets/kalshi_private.key
```

---

# .gitignore Requirements

The repository MUST contain at least:

```gitignore
# Environment variables
.env
.env.*
!.env.example

# Secrets
secrets/
*.key
*.pem

# Python
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Local application data
*.db
*.sqlite
*.sqlite3
```

Before every commit involving configuration:

```bash
git status
```

Confirm no secrets are staged.

---

# .env.example

The repository SHOULD include:

```dotenv
# SportsGameOdds
SPORTS_GAME_ODDS_API_KEY=replace_me

# Calendar-day filtering
APP_TIMEZONE=America/Chicago

# Kalshi
KALSHI_ENVIRONMENT=production

# Needed only if authenticated Kalshi functionality is added later.
# KALSHI_API_KEY_ID=
# KALSHI_PRIVATE_KEY_PATH=./secrets/kalshi_private.key
```

`.env.example` must never contain genuine credentials.

---

# Configuration

Create configuration centrally.

Example responsibilities:

```python
SPORTS_GAME_ODDS_API_KEY
APP_TIMEZONE
KALSHI_ENVIRONMENT
```

Fail immediately with a clear error if a required secret is missing.

Example:

```text
SPORTS_GAME_ODDS_API_KEY is required.
Create a local .env file using .env.example.
```

Never silently fall back to a fake key.

---

# Time Handling

Time filtering is critical.

Do NOT interpret "today" as UTC.

"Today" means the current calendar date in:

```text
APP_TIMEZONE
```

Default:

```text
America/Chicago
```

Use Python's:

```python
zoneinfo.ZoneInfo
```

Do not install `pytz`.

---

# Today's Event Window

For every request:

1. Get the current time in `APP_TIMEZONE`.
2. Determine local midnight at the start of today.
3. Determine local midnight at the beginning of tomorrow.
4. Convert both values to UTC.
5. Treat the valid interval as:

```text
[start_of_today, start_of_tomorrow)
```

The upper boundary must be exclusive.

Conceptually:

```python
local_now = datetime.now(timezone)

start_local = local_now.replace(
    hour=0,
    minute=0,
    second=0,
    microsecond=0,
)

end_local = start_local + timedelta(days=1)

start_utc = start_local.astimezone(UTC)
end_utc = end_local.astimezone(UTC)
```

Do not hard-code UTC offsets because daylight-saving time changes.

---

# Event Eligibility Rule

An event is valid only when ALL conditions are true:

```text
event.start_time >= start_of_today
AND
event.start_time < start_of_tomorrow
AND
event.started == false
AND
event has available odds
```

Additionally perform a local validation after receiving the API response.

Never assume upstream filtering is perfect.

---

# SportsGameOdds Integration

## Purpose

SportsGameOdds is the sportsbook-data source.

Use it to retrieve:

* events;
* start times;
* leagues;
* players;
* sportsbook prices;
* player props;
* opposing outcomes.

---

# SportsGameOdds Authentication

Use the API key through the:

```text
x-api-key
```

HTTP header.

Prefer headers over query-string authentication so secrets are less likely to appear in:

* logs;
* browser history;
* proxy logs;
* error messages.

Conceptual request:

```python
headers = {
    "x-api-key": settings.sports_game_odds_api_key
}
```

Never construct URLs containing the real API key.

---

# SportsGameOdds Event Endpoint

Use:

```text
GET /v2/events
```

Current relevant parameters include:

```text
oddsAvailable=true
started=false
startsAfter=<UTC datetime>
startsBefore=<UTC datetime>
leagueID=<optional league filters>
limit=<page size>
cursor=<pagination cursor>
```

Use server-side filtering wherever possible.

DO NOT:

```text
download hundreds of games
then filter today locally
```

when the API can filter before returning them.

---

# Required SportsGameOdds Request

Conceptually:

```text
GET /v2/events
    ?oddsAvailable=true
    &started=false
    &startsAfter=<start UTC>
    &startsBefore=<tomorrow UTC>
```

League filters may be added later.

Example logical parameters:

```python
params = {
    "oddsAvailable": "true",
    "started": "false",
    "startsAfter": start_utc.isoformat(),
    "startsBefore": end_utc.isoformat(),
}
```

The precise serialization should follow the current API documentation.

---

# Important Date Rule

Do not use:

```text
now + 24 hours
```

as the definition of today.

Incorrect:

```text
2:30 PM today -> 2:30 PM tomorrow
```

Correct:

```text
12:00 AM today -> 12:00 AM tomorrow
```

in `APP_TIMEZONE`.

---

# SportsGameOdds Response

The response uses a structure containing:

```text
success
data
nextCursor
```

The application should primarily consume:

```text
data
```

and continue pagination only when:

```text
nextCursor
```

is present.

---

# Pagination

Implement one small reusable loop.

Pseudo-code:

```python
cursor = None

while True:
    response = get_events(cursor=cursor)

    yield from response["data"]

    cursor = response.get("nextCursor")

    if not cursor:
        break
```

Do not build a generic pagination framework.

---

# Player Props

SportsGameOdds returns player props as part of event odds.

Player-based markets can be identified through their stat entity/player identifiers rather than team-level entities.

Relevant normalized concepts include:

```text
event_id
league
player_id
player_name
stat
period
side
line
sportsbook
american_odds
available
```

---

# Sportsbook Odds Normalization

Internal odds records should use a simple structure.

Example:

```python
@dataclass(frozen=True)
class SportsbookQuote:
    event_id: str
    player_id: str | None
    player_name: str | None
    stat: str
    period: str
    side: str
    line: float | None
    sportsbook: str
    american_odds: int
```

Only add fields that are actually consumed.

Do not duplicate the entire API response into internal models.

---

# Numerical Parsing

The SportsGameOdds API may return odds/line values as strings.

Convert them at the boundary.

For example:

```python
american_odds = int(raw_odds)
line = float(raw_line)
```

Do not pass string-encoded numeric values throughout the application.

---

# Sportsbook Availability

Only retain bookmaker quotes when the quote is currently available.

If a bookmaker entry reports:

```text
available = false
```

ignore it.

Do not include stale/unavailable lines in consensus calculations later.

---

# Opposing Markets

Where needed, retrieve both sides of an over/under:

```text
OVER
UNDER
```

Later de-vigging will require both sides.

Current implementation should preserve both rather than selecting only the over.

---

# Alternate Lines

Do not enable alternate lines unless explicitly required.

Default behavior should favor main lines to reduce:

* API response size;
* market-matching complexity;
* duplicate markets.

---

# SportsGameOdds API Documentation

Before changing API request parameters or response parsing, consult the official SportsGameOdds documentation.

Relevant documentation sections:

```text
Documentation
Quickstart
GET /events
Odds Data Type
Markets
Player Props API
API Cheat Sheet
```

Do not guess undocumented fields.

If the API response differs from existing code:

1. inspect the actual response;
2. consult current official documentation;
3. make the smallest required code change.

---

# Kalshi Integration

## Current Purpose

Kalshi is currently a READ-ONLY prediction-market data source.

Use it to retrieve:

* open markets;
* market tickers;
* event tickers;
* titles/subtitles;
* YES prices;
* NO prices;
* volume;
* open interest;
* market status;
* market timestamps.

Do not place orders in the current scope.

---

# Kalshi Environment

Support:

```text
production
demo
```

with one configuration switch.

Do not scatter environment URLs throughout the codebase.

Use one base URL configured in `config.py`.

---

# Kalshi Public Market Data

Public market data can be retrieved without authenticated trading credentials.

Prefer public endpoints for the current scanner.

Relevant endpoints include:

```text
GET /markets
GET /markets/{ticker}
GET /markets/{ticker}/orderbook
GET /events
GET /events/{event_ticker}
```

---

# Kalshi Market Request

Only request markets that are currently open.

Use:

```text
status=open
```

Conceptually:

```python
params = {
    "status": "open",
}
```

Handle cursor pagination.

---

# Kalshi Event Eligibility

Kalshi's market status alone does NOT establish whether the underlying sporting event has begun.

For this application, SportsGameOdds is the canonical game-start source.

Therefore:

```text
SportsGameOdds event
        |
        | verified same-day + started=false
        v
matching Kalshi market
```

A Kalshi market must not independently cause an event to be treated as eligible.

---

# Do Not Use Kalshi close_time as Game Start Time

These concepts are not guaranteed to mean the same thing:

```text
sporting-event start time
Kalshi market close time
```

Do not substitute one for the other.

Use the matched SportsGameOdds event start time to determine whether the sporting event is eligible.

---

# Kalshi Prices

For simple scanning, use current executable pricing rather than last traded price whenever possible.

Relevant market fields include concepts such as:

```text
yes_bid
yes_ask
no_bid
no_ask
last_price
volume
open_interest
```

Do NOT use:

```text
last_price
```

as if it were automatically the price currently available to buy.

A trade may have occurred earlier at a price no longer available.

---

# Kalshi Order Book

Use order-book data only when needed.

Current order books represent:

```text
YES bids
NO bids
```

For binary contracts:

```text
YES ask = 1.00 - best NO bid
NO ask  = 1.00 - best YES bid
```

When market-level ask fields are sufficient, do not make an extra order-book request unnecessarily.

This keeps API calls minimal.

---

# Kalshi Pagination

Kalshi uses cursor-based pagination.

Implement one small loop.

Pseudo-code:

```python
cursor = None

while True:
    params = {"status": "open"}

    if cursor:
        params["cursor"] = cursor

    payload = request_markets(params)

    yield from payload["markets"]

    cursor = payload.get("cursor")

    if not cursor:
        break
```

---

# Kalshi Authentication

Authentication is NOT necessary for normal public-market retrieval.

Do not add signing logic until an authenticated endpoint is actually required.

If authenticated functionality is later added, Kalshi currently uses request headers conceptually equivalent to:

```text
API key ID
request timestamp
RSA-signed request
```

The signature uses:

```text
timestamp + HTTP method + request path
```

with query parameters excluded from the signed path.

Do not reimplement authentication differently from Kalshi's official documentation.

---

# Kalshi Trading

AUTOMATED TRADING IS OUT OF SCOPE.

No current module should:

```text
POST an order
cancel an order
modify an order
fetch balances for execution
automatically buy YES
automatically buy NO
```

If trading is later implemented:

1. build it as a separate module;
2. default to demo;
3. require an explicit configuration switch;
4. require risk controls;
5. use unique client order IDs;
6. use limit orders;
7. implement duplicate-order prevention;
8. never silently fall back from demo to production.

Do not add this now.

---

# Kalshi API Documentation

Before changing Kalshi request logic, consult the current official documentation.

Relevant sections:

```text
Quick Start: Market Data
Get Markets
Get Market
Get Events
Get Market Orderbook
Orderbook Responses
Market Lifecycle
API Environments
Authenticated Requests
```

Do not infer API behavior from older blog posts or unofficial examples when official documentation exists.

---

# Market Matching

Market matching should initially be conservative.

Do not attempt fuzzy matching until exact or normalized matching has been attempted.

Potential matching inputs:

```text
league
home team
away team
game date
player name
stat
threshold
direction
```

The system should prefer:

```text
NO MATCH
```

over an uncertain match.

A false positive is worse than failing to match a market.

---

# Normalization

Normalize strings before comparison.

Suggested normalization:

```text
lowercase
strip whitespace
collapse repeated spaces
remove harmless punctuation
normalize common team abbreviations
```

Do not aggressively transform names in ways that could merge different players.

Example:

```python
def normalize_name(value: str) -> str:
    return " ".join(value.lower().strip().split())
```

Start simple.

Add special-case mappings only when real data demonstrates they are required.

---

# Same-Day Matching Requirement

The SportsGameOdds event must first pass:

```text
today
AND
not started
```

Only then search for corresponding Kalshi markets.

Never do:

```text
Kalshi market found
=> assume game is eligible
```

---

# Canonical Event Model

Use a minimal event representation:

```python
@dataclass(frozen=True)
class Event:
    event_id: str
    league: str
    home_team: str
    away_team: str
    start_time_utc: datetime
```

If fields are unnecessary, do not add them.

---

# Canonical Prediction Market Model

Example:

```python
@dataclass(frozen=True)
class PredictionMarket:
    ticker: str
    event_ticker: str
    title: str
    yes_bid: Decimal | None
    yes_ask: Decimal | None
    no_bid: Decimal | None
    no_ask: Decimal | None
```

Use `Decimal` for money/prices where practical.

Avoid floating-point arithmetic for actual monetary execution if trading is added later.

---

# Error Handling

Keep errors explicit and simple.

Handle:

```text
network timeout
HTTP 4xx
HTTP 5xx
429 rate limit
invalid JSON
missing required response data
```

Do not suppress exceptions with broad:

```python
except Exception:
    pass
```

If retrying:

* retry only transient failures;
* use a small retry count;
* use modest backoff;
* respect rate-limit responses.

Do not build an elaborate retry framework.

---

# HTTP Client

Prefer one shared `httpx.Client`.

Example:

```python
with httpx.Client(timeout=10.0) as client:
    ...
```

Do not create a new client for every individual market request unnecessarily.

Set a reasonable timeout.

No request should hang indefinitely.

---

# Logging

Use Python's built-in:

```python
logging
```

Log:

```text
number of SportsGameOdds events fetched
number of eligible same-day events
number of Kalshi markets fetched
number of matches
API failures
```

Do not log:

```text
API keys
private keys
authentication signatures
full secret-bearing headers
```

Default logging level:

```text
INFO
```

---

# Output

For the current MVP, terminal output is sufficient.

Example:

```text
Upcoming games today: 4

NBA
BOS @ DAL
Start: 7:30 PM CT
Sportsbook markets: 182
Kalshi matches: 14
```

Do not build a GUI.

Do not build a website.

Do not add a database unless persistence becomes necessary.

---

# No Started Games

This rule is non-negotiable.

Before outputting an event, verify:

```python
event.start_time_utc > current_time_utc
```

This provides a secondary local protection even when:

```text
started=false
```

was sent to SportsGameOdds.

If:

```text
event.start_time <= now
```

discard it.

This prevents an event from slipping through because of delayed provider status updates.

---

# Request-Time Race Condition

A game may start between:

```text
initial API fetch
and
later processing
```

Therefore perform start-time validation as close as practical to final usage.

For the current read-only scanner:

```text
fetch
normalize
validate current time
output
```

For any future execution system, game-start validation must happen again immediately before execution.

---

# Testing Requirements

Keep tests focused.

Required areas:

## Time window

Test:

```text
middle of day
just after midnight
just before midnight
DST transition
```

Verify resulting UTC boundaries are correct.

---

## Event filtering

Test:

```text
game later today -> included
game already started today -> excluded
game tomorrow -> excluded
game yesterday -> excluded
```

---

## SportsGameOdds parsing

Mock a small API response containing:

```text
two events
two sportsbooks
over/under prop
unavailable bookmaker quote
```

Verify unavailable quotes are discarded.

---

## Kalshi parsing

Mock:

```text
open market
closed market
YES bid/ask
NO bid/ask
```

Verify only expected fields are normalized.

---

## Secrets

Tests must never require real API credentials.

Use placeholder values.

---

# Testing Philosophy

Do not test implementation details.

Test observable behavior.

Avoid enormous fixtures.

Prefer small hand-written JSON samples over copied full API responses.

---

# Commands

Create virtual environment:

```bash
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install:

```bash
pip install -r requirements.txt
```

Run:

```bash
python -m src.main
```

Tests:

```bash
pytest
```

---

# requirements.txt

Keep minimal:

```text
httpx
python-dotenv
pytest
```

Do not pin dozens of transitive dependencies manually.

Version pinning can be added once the prototype is stable.

---

# Implementation Order

Claude should implement features in this order.

## Phase 1 — Configuration

Create:

```text
.gitignore
.env.example
src/config.py
```

Confirm secrets cannot be committed accidentally.

---

## Phase 2 — Time Window

Implement:

```python
get_today_utc_window()
```

Returning:

```text
start_utc
end_utc
```

based on `APP_TIMEZONE`.

Add tests.

---

## Phase 3 — SportsGameOdds

Implement only:

```python
get_todays_upcoming_events()
```

It must:

```text
use start/end bounds
use started=false
use oddsAvailable=true
handle pagination
locally reject started events
```

Do not implement unrelated endpoints.

---

## Phase 4 — Kalshi

Implement only:

```python
get_open_markets()
```

Handle pagination.

No authentication required for current read-only market retrieval.

---

## Phase 5 — Normalization

Normalize only fields necessary for matching.

Do not attempt full market matching until real sample data is available.

---

## Phase 6 — Output

Display:

```text
eligible events
basic sportsbook-market counts
potential Kalshi market matches
```

No EV calculation yet unless explicitly requested.

---

# Claude Coding Workflow

When working on this repository:

1. Read this `CLAUDE.md`.
2. Inspect existing files before creating new ones.
3. Reuse existing functions where reasonable.
4. Make the smallest change that satisfies the request.
5. Do not refactor unrelated code.
6. Do not implement future features.
7. Run relevant tests.
8. Fix failures caused by the change.
9. Review `git diff`.
10. Check for secrets before completion.

---

# Before Writing Code

Claude should first determine:

```text
Does this already exist?
Can the requirement be satisfied by modifying one function?
Can an existing dependency handle it?
Is this feature actually requested?
```

If the answer to the final question is no:

```text
do not implement it
```

---

# Change Size Discipline

Prefer:

```text
one feature
one focused change
one focused test group
```

Avoid combining:

```text
feature implementation
large refactor
dependency changes
formatting entire repository
```

in the same task.

---

# Comments

Comments should explain WHY, not obvious syntax.

Good:

```python
# Treat "today" in the configured local timezone before converting
# to UTC; otherwise evening games can be assigned to the wrong date.
```

Bad:

```python
# Increment i
i += 1
```

---

# Docstrings

Use short docstrings for public functions.

Example:

```python
def get_today_utc_window() -> tuple[datetime, datetime]:
    """Return today's local calendar-day boundaries converted to UTC."""
```

Do not write essay-length docstrings.

---

# Function Size

Prefer functions that do one obvious task.

Do not enforce arbitrary line limits, but reconsider functions that become difficult to understand at a glance.

---

# Naming

Use explicit names.

Prefer:

```python
start_utc
event_start
sportsbook_quote
market_ticker
```

Avoid:

```python
x
data2
thing
temp
obj
```

except trivial local loops.

---

# No Premature Optimization

Do not optimize before measurement.

Current expected data volume does not require:

```text
multiprocessing
distributed jobs
Redis
Kafka
Celery
Kubernetes
```

Do not introduce them.

---

# API Efficiency

Minimize API calls.

Prefer:

```text
one filtered SportsGameOdds events request
plus required pagination
```

rather than separate requests per event.

Prefer:

```text
one paginated Kalshi market retrieval
```

rather than one request per market.

Only query individual Kalshi market/order-book endpoints after a likely match exists.

---

# API Rate Limits

Treat rate limits conservatively.

If HTTP 429 occurs:

1. stop rapid repeated requests;
2. respect retry information if provided;
3. wait using bounded backoff;
4. do not create parallel retry storms.

---

# Data Freshness

Every API fetch should retain a local:

```text
fetched_at_utc
```

timestamp.

This will matter later when EV calculations are implemented.

For now, it can be attached to the returned batch rather than every individual quote.

---

# Security Review Before Completion

Before finishing any task touching APIs, verify:

```text
[ ] No API key appears in source code
[ ] No private key appears in source code
[ ] .env is ignored
[ ] secrets/ is ignored
[ ] *.key is ignored
[ ] API key is passed via header
[ ] No secret-bearing request is logged
[ ] Tests contain only fake credentials
```

---

# Current Acceptance Criteria

The current project is complete when running:

```bash
python -m src.main
```

does the following:

1. Determines today's date using `APP_TIMEZONE`.
2. Creates today's local midnight-to-midnight range.
3. Converts that interval to UTC.
4. Calls SportsGameOdds using server-side filters for:

   * start after today's lower bound;
   * start before tomorrow's lower bound;
   * `started=false`;
   * `oddsAvailable=true`.
5. Handles SportsGameOdds pagination.
6. Re-validates every returned event locally.
7. Removes any event whose start time is already in the past.
8. Retrieves currently open Kalshi markets.
9. Handles Kalshi pagination.
10. Produces normalized read-only output.
11. Does not place any trade.
12. Does not expose any secret.
13. Passes tests.

---

# Explicit Non-Goals

Do not implement these until specifically requested:

```text
EV calculation
vig removal
weighted sportsbook consensus
sharp-book weighting
automatic betting
Kalshi order placement
position management
Kelly criterion
bankroll tracking
alerts
Discord integration
SMS
email
historical backtesting
database storage
web dashboard
GUI
machine learning
sportsbook scraping
live-game trading
```

---

# Future Architecture Guideline

When future features are requested, preserve this directional dependency:

```text
API clients
    |
    v
normalized data
    |
    v
market matching
    |
    v
fair-value calculation
    |
    v
opportunity detection
    |
    v
risk checks
    |
    v
execution
```

Higher layers may depend on lower layers.

Lower layers must NOT depend on trading logic.

For example:

```text
sports_odds.py
```

must never know whether an opportunity will be traded.

---

# Future Trading Safety Boundary

If automated Kalshi execution is eventually requested, create a strict separation:

```text
market scanner
      |
      v
signal
      |
      v
risk validation
      |
      v
execution
```

The scanner must never directly place orders.

Execution must be independently disableable.

Default:

```text
TRADING_ENABLED=false
```

Production execution must require explicit configuration.

Do not implement this until requested.

---

# Source-of-Truth Rules

For game scheduling/start state:

```text
SportsGameOdds event start time
```

is the current canonical source.

For sportsbook prices:

```text
SportsGameOdds
```

is the source.

For Kalshi market pricing/status:

```text
Kalshi
```

is the source.

Never infer one provider's state from another when the provider exposes the relevant field directly.

---

# Final Rule

When uncertain between:

```text
more code
```

and:

```text
less code
```

choose less code unless additional complexity is required for correctness, security, or an explicitly requested feature.

Correctness and secret protection take priority over minimalism.

Never sacrifice those for fewer lines.
