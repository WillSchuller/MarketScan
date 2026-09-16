# Handoff Notes

Read this first, then `CLAUDE.md` (full spec/philosophy for this project). This file is
session-to-session continuity context; `CLAUDE.md` is the durable ruleset.

Last updated: 2026-09-16. Repo: `github.com/WillSchuller/MarketScan`, branch `main`,
local and `origin/main` both at commit `b62cfb4`. Working tree clean.

## What this project is

Read-only Python scanner: fetches today's sportsbook odds (SportsGameOdds) and Kalshi
prediction markets, filtered to events that haven't started and start today (local
calendar day, `APP_TIMEZONE`). No trading, no EV calc yet — see "Explicit Non-Goals" in
`CLAUDE.md`.

## Environment setup (already done, should persist)

- `.venv/` exists at repo root with `httpx`, `python-dotenv`, `pytest`, and `tzdata`
  (Windows needs `tzdata` for `zoneinfo` — there's no system IANA tz database on Windows).
- `.env` exists locally with a **real** `SPORTS_GAME_ODDS_API_KEY` and `APP_TIMEZONE`.
  It is git-ignored — never read its contents into a commit, log, or this file.
- Run tests: `.venv\Scripts\python.exe -m pytest -v` (or activate with
  `.venv\Scripts\Activate.ps1` first). Currently **18 tests, all passing**.

## Progress vs. CLAUDE.md's phase plan

- [x] **Phase 1 — Configuration**: `src/config.py` (`load_settings()`), `.env.example`,
      `.gitignore` hardened to the full secrets list CLAUDE.md requires.
- [x] **Phase 2 — Time Window**: `src/time_utils.py` (`get_today_utc_window`), DST-tested.
- [x] **Phase 3 — SportsGameOdds**: `src/sports_odds.py` (`get_todays_upcoming_events`),
      `src/models.py` (`Event`). Tests use `league_ids="NFL,MLB"` and mix both leagues.
- [ ] **Phase 4 — Kalshi**: not started. Next up.
- [ ] **Phase 5 — Normalization**: not started (`SportsbookQuote`, `PredictionMarket`
      dataclasses; the odds-parsing side of `sports_odds.py` hasn't been touched yet —
      only event-level fields have been implemented so far, no odds/props parsing).
- [ ] **Phase 6 — Output**: not started.

## Key facts learned this session (not guesses — verified against real API responses/docs)

- SportsGameOdds base URL: `https://api.sportsgameodds.com/v2`.
- Auth: `x-api-key` header works (confirmed live) — matches CLAUDE.md's header
  preference; the docs also mention a query-param alternative (`apiKey=`), which we're
  intentionally not using.
- `GET /events` response shape: `{success, data: [Event], nextCursor}`.
- Event fields actually used: `eventID`, `leagueID`, `teams.home/away.names.long`,
  `status.startsAt` (ISO 8601 UTC, `Z` suffix), `status.started`.
- **Important constraint**: the current API key's subscription tier rejects requests
  that don't include `leagueID` or `eventID` (400: "You must specify either a leagueID
  or an eventID at this subscription tier"). This is why `get_todays_upcoming_events()`
  takes an optional `league_ids` param instead of querying all leagues at once — pass
  something like `"NFL,MLB"`. If the plan is ever upgraded, this constraint may no
  longer apply, but don't remove the parameter — just stop requiring it be set.
- Odds/bookmaker/player-prop response shape has **not** been inspected yet — that's
  needed before starting Phase 5 (see "Odds Structure" section fetched from docs during
  Phase 3, but not verified live: `oddID`, `marketName`, `statID`, `betTypeID`,
  `fairOdds`, `bookOdds`, `byBookmaker`).

## Working pattern established with the user this session

- Implement one phase at a time. Write tests immediately after each part, run them,
  confirm passing, before moving on.
- Tests use `httpx.MockTransport` — no real network calls, no real credentials in test
  files (use `"fake-key"` placeholders).
- Before committing: `git status` / review diff for secrets (the user's CLAUDE.md has an
  explicit pre-commit secrets checklist).
- Commit only when the user explicitly asks ("commit changes"); push only when the user
  explicitly asks ("push them") — these are treated as separate approvals.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Keep changes minimal and scoped to the requested phase — don't jump ahead into later
  phases (e.g. don't start odds normalization while doing event fetching).

## Suggested next step

Start **Phase 4 — Kalshi**: implement `get_open_markets()` in `src/kalshi.py`, hitting
Kalshi's public `GET /markets?status=open` (production/demo base URL switch in
`src/config.py` — Kalshi env var already exists as `KALSHI_ENVIRONMENT`, just needs a
base-URL mapping added), cursor pagination, no auth required for public market data.
Consult Kalshi's official docs for the exact base URLs and response shape rather than
guessing (same approach used for SportsGameOdds this session — a live smoke-test call
without real credentials is fine since public endpoints don't need auth). Add
`tests/test_kalshi.py` with mocked responses (open market, closed market, YES/NO
bid/ask) per CLAUDE.md's testing requirements.
