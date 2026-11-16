from decimal import Decimal

from src.dashboard import Bet, kelly_fraction, parse_bets, render_page, settle

LINE = (
    "1. NBA: Julian Champagnie rebounds 5.5 Over -- KXNBAREB-26OCT20OKCSAS-SASJCHAMPAGNIE30-6 "
    "YES $0.39 x 1 -- Net EV: +4.46%; Gross EV: +8.93% -- Entry fee: $0.0167; Total cost: $0.4067 "
    "-- Expected net profit: $+0.0181 -- Fair odds: +135"
)


def test_parse_bets_recovers_cost_and_fair_probability():
    bets = parse_bets(LINE + "\nnot a bet line\n")

    assert len(bets) == 1
    assert bets[0].ticker == "KXNBAREB-26OCT20OKCSAS-SASJCHAMPAGNIE30-6"
    assert bets[0].side == "YES"
    assert bets[0].cost == Decimal("0.4067")
    assert bets[0].fair_probability == Decimal("0.4248")


def test_kelly_fraction_for_binary_contract():
    # p=0.5 at cost 0.4: b=1.5, f* = (1.5*0.5 - 0.5)/1.5 = 1/6
    assert kelly_fraction(Decimal("0.5"), Decimal("0.4")) == Decimal(1) / Decimal(6)
    assert kelly_fraction(Decimal("0.3"), Decimal("0.4")) == 0


def test_settle_win_loss_pending():
    bet = Bet("x", "T", "NO", Decimal("0.4"), Decimal("0.5"))
    stake = Decimal(1000) * Decimal("0.1") / Decimal(6)

    win = settle(bet, "no")
    loss = settle(bet, "yes")
    pending = settle(bet, "")

    assert win.outcome == "win" and win.profit == stake * Decimal("1.5")
    assert loss.outcome == "loss" and loss.profit == -stake
    assert pending.outcome == "pending" and pending.profit == 0


def test_render_page_shows_final_bankroll():
    bet = Bet("x", "T", "YES", Decimal("0.4"), Decimal("0.5"))
    page = render_page([settle(bet, "no")])

    assert "Final bankroll: <b>$983.33</b>" in page
