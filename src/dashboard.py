"""Local test dashboard: settle opportunities.txt bets on Kalshi and simulate 10% Kelly.

Run with `python -m src.dashboard`, then open http://127.0.0.1:8000 .
Read-only: it only fetches public Kalshi market results and never places orders.
"""

from __future__ import annotations

import html
import logging
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from src.config import KALSHI_BASE_URLS
from src.kalshi import get_market_result
from src.main import OPPORTUNITIES_FILE

logger = logging.getLogger(__name__)

STARTING_BANKROLL = Decimal(1000)
KELLY_FRACTION = Decimal("0.1")

# Matches the lines written by src.main._ranked_opportunity_lines.
LINE_PATTERN = re.compile(
    r"^\d+\. (?P<description>.+?) -- (?P<ticker>\S+) (?P<side>YES|NO) "
    r"\$(?P<price>[\d.]+) x (?P<contracts>\d+) -- .*?"
    r"Total cost: \$(?P<total_cost>[\d.]+) -- "
    r"Expected net profit: \$(?P<expected_profit>[+-]?[\d.]+)"
)


@dataclass(frozen=True)
class Bet:
    description: str
    ticker: str
    side: str
    cost: Decimal  # fee-inclusive cost per contract; each contract pays $1 if it wins
    fair_probability: Decimal


@dataclass(frozen=True)
class BetResult:
    bet: Bet
    stake: Decimal
    outcome: str  # "win", "loss", or "pending"
    profit: Decimal


def parse_bets(text: str) -> list[Bet]:
    """Parse opportunities.txt lines; lines in an unexpected format are skipped."""
    bets: list[Bet] = []
    for line in text.splitlines():
        match = LINE_PATTERN.match(line.strip())
        if match is None:
            continue
        contracts = Decimal(match["contracts"])
        total_cost = Decimal(match["total_cost"])
        # The file rounds fair odds to whole American odds, so recover the
        # more precise probability from expected profit = C * p - total_cost.
        fair_probability = (Decimal(match["expected_profit"]) + total_cost) / contracts
        bets.append(
            Bet(
                description=match["description"],
                ticker=match["ticker"],
                side=match["side"],
                cost=total_cost / contracts,
                fair_probability=fair_probability,
            )
        )
    return bets


def kelly_fraction(fair_probability: Decimal, cost: Decimal) -> Decimal:
    """Full-Kelly bankroll fraction for a $1-payout contract bought at `cost`."""
    # Net odds b = (1 - cost) / cost, so f* = p - (1 - p) / b = (p - cost) / (1 - cost).
    return max(Decimal(0), (fair_probability - cost) / (1 - cost))


def settle(bet: Bet, result: str, bankroll: Decimal = STARTING_BANKROLL) -> BetResult:
    """Size the bet at 10% Kelly of `bankroll` and score it against Kalshi's result."""
    stake = bankroll * KELLY_FRACTION * kelly_fraction(bet.fair_probability, bet.cost)
    if result not in ("yes", "no"):
        return BetResult(bet, stake, "pending", Decimal(0))
    if result == bet.side.lower():
        return BetResult(bet, stake, "win", stake * (1 - bet.cost) / bet.cost)
    return BetResult(bet, stake, "loss", -stake)


def _fetch_results(bets: list[Bet]) -> list[BetResult]:
    base_url = KALSHI_BASE_URLS[os.getenv("KALSHI_ENVIRONMENT", "production")]
    results: list[BetResult] = []
    with httpx.Client(timeout=10.0) as client:
        for bet in bets:
            try:
                result = get_market_result(base_url, client, bet.ticker)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                logger.warning("Could not fetch result for %s: %s", bet.ticker, exc)
                result = ""
            # Every bet is placed up front from the same starting bankroll,
            # since all scanned bets are taken before any of the games settle.
            results.append(settle(bet, result))
    return results


def render_page(results: list[BetResult]) -> str:
    total_staked = sum((r.stake for r in results), Decimal(0))
    total_profit = sum((r.profit for r in results), Decimal(0))
    final_bankroll = STARTING_BANKROLL + total_profit
    counts = {name: sum(r.outcome == name for r in results) for name in ("win", "loss", "pending")}

    rows = "".join(
        f"<tr class='{r.outcome}'><td>{html.escape(r.bet.description)}</td>"
        f"<td><code>{html.escape(r.bet.ticker)}</code></td><td>{r.bet.side}</td>"
        f"<td>${r.bet.cost:.4f}</td><td>{r.bet.fair_probability:.2%}</td>"
        f"<td>${r.stake:.2f}</td><td>{r.outcome}</td><td>${r.profit:+.2f}</td></tr>"
        for r in results
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Bet Results Test</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; background: #fff; color: #222; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 14px; }}
tr.win td:last-child {{ color: #1a7f37; }} tr.loss td:last-child {{ color: #cf222e; }}
tr.pending {{ color: #888; }}
.summary span {{ display: inline-block; margin-right: 24px; font-size: 18px; }}
</style></head><body>
<h1>Bet results test (10% Kelly, ${STARTING_BANKROLL:,.0f} start)</h1>
<p class="summary">
<span>Final bankroll: <b>${final_bankroll:,.2f}</b></span>
<span>P&amp;L: <b>${total_profit:+,.2f}</b></span>
<span>Staked: ${total_staked:,.2f}</span>
<span>W/L/Pending: {counts['win']}/{counts['loss']}/{counts['pending']}</span>
</p>
<p>Source: {html.escape(str(OPPORTUNITIES_FILE))}. All bets are sized from the starting bankroll
at fee-inclusive cost; fractional contracts are allowed. Pending bets have no P&amp;L yet.</p>
<table><tr><th>Bet</th><th>Ticker</th><th>Side</th><th>Cost/contract</th><th>Fair prob</th>
<th>Stake</th><th>Outcome</th><th>P&amp;L</th></tr>{rows}</table>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        text = OPPORTUNITIES_FILE.read_text(encoding="utf-8") if OPPORTUNITIES_FILE.exists() else ""
        body = render_page(_fetch_results(parse_bets(text))).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Bind to localhost only; this is a personal test tool, not a public site.
    server = HTTPServer(("127.0.0.1", 8000), _Handler)
    print("Dashboard running at http://127.0.0.1:8000 (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
