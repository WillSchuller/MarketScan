# MarketScan

> This project started as practice in agent-based coding (building software by
> directing an AI coding agent) for Senior Design. It is a learning prototype,
> not a production trading system.

## How it works

MarketScan is a read-only scanner that compares sportsbook odds against Kalshi
prediction-market prices for today's games.

1. **Today's window.** Works out midnight-to-midnight for today in
   `APP_TIMEZONE` and converts it to UTC.
2. **Sportsbook odds.** Pulls today's games that have not started and have odds
   available from SportsGameOdds, including moneylines and player props. Each
   game is checked again locally so games that have already started are dropped.
3. **Kalshi markets.** Pulls open Kalshi game and player-prop markets from the
   public API. No login is needed.
4. **Matching.** Pairs each sportsbook market with its Kalshi equivalent, and
   prefers no match over a doubtful one.
5. **Fair value.** Removes the vig from each sportsbook's two-sided odds and
   averages across books to get a fair probability.
6. **Net EV.** Compares the fair probability to the Kalshi ask after Kalshi's
   estimated taker fee. Positive-EV bets are ranked and written to
   `opportunities.txt` on the Desktop.

No orders are ever placed.

## The dashboard: testing the design live

The scanner says which bets *should* be profitable. The dashboard checks
whether they actually were. It is how we test the design against real outcomes
instead of trusting the math on its own.

- It reads the bets saved in `opportunities.txt`.
- It looks up each market's final result on Kalshi's public API.
- It simulates a $1,000 bankroll that stakes 10% Kelly on each bet, and shows
  each bet's outcome and P&L along with the final bankroll and win/loss/pending
  counts.

If the simulated bankroll grows over many settled bets, that supports the
de-vig, matching, and fee assumptions. If it shrinks, one of those steps needs
work. The dashboard is read-only and only simulates money.

## Running it

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt
cp .env.example .env              # then add your SportsGameOdds API key

python -m src.main                # run the scanner
python -m src.dashboard           # then open http://127.0.0.1:8000
python -m pytest                  # run the tests
```

Optional settings (`EV_CONTRACTS`, `KALSHI_TAKER_FEE_MULTIPLIER`,
`KALSHI_BALANCE_PRECISION`, `LEAGUE_IDS`) are documented in `.env.example`. Fee
estimates follow Kalshi's
[fee schedule](https://kalshi.com/docs/kalshi-fee-schedule.pdf) and
[fee-rounding rules](https://docs.kalshi.com/getting_started/fee_rounding).
