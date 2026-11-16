"""Fee, ROI, side-selection and global-ranking regression tests."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import importlib

import pytest

from src.config import Settings, load_settings
from src.models import Event, PlayerPropMarket, PredictionMarket, SportsbookQuote
from src.valuation import FeePolicy, Opportunity, calculate_net_value, rank_opportunities

app = importlib.import_module('src.main')


def test_known_fee_and_all_in_roi():
    result = calculate_net_value(D('.43'), D('.40'))
    assert result.entry_cost == D('.40')
    assert result.entry_fee == D('.0168')
    assert result.total_cost == D('.4168')
    assert result.expected_profit == D('.0132')
    assert result.gross_ev == D('.075')
    assert abs(result.net_ev - D(33)/1042) < D('1e-26')


def test_fcm_cent_rounding_and_quantity():
    policy = FeePolicy(balance_precision=D('.01'))
    result = calculate_net_value(D('.43'),D('.4'),policy)
    assert result.entry_fee == D('.02')
    assert result.total_cost == D('.42')
    assert result.net_ev == D(1)/42
    hundred = calculate_net_value(D('.43'),D('.4'),replace(policy, contracts=100))
    assert hundred.entry_fee == D('1.68')
    assert hundred.expected_profit == D('1.32')
    assert hundred.net_ev > result.net_ev  # Rounds once for the position, not per contract.


def test_trade_fee_then_position_cost_round_up_subcent():
    # Revenue is not on the account's precision grid. Rounding the fee alone
    # would incorrectly charge .0037 rather than .00365 in this example.
    value = calculate_net_value(D('.1'),D('.05505'))
    assert value.entry_fee == D('.00365')
    assert value.total_cost == D('.0587')


def test_fcm_worked_rounding_example():
    value = calculate_net_value(D('.1'),D('.055'),FeePolicy(balance_precision=D('.01')))
    assert value.entry_fee == D('.005')
    assert value.total_cost == D('.06')


@pytest.mark.parametrize('precision', ['.010', '.0100', '.000100'])
def test_precision_spelling_does_not_change_rounding(precision):
    policy=FeePolicy(balance_precision=D(precision))
    canonical=FeePolicy(balance_precision=D(precision).normalize())
    assert calculate_net_value(D('.43'),D('.4'),policy) == calculate_net_value(D('.43'),D('.4'),canonical)


@pytest.mark.parametrize('p,price,expected_profit', [('.5','.5','-.0175'),('.6','.5','.0825'),('.35','.4','-.0668')])
def test_fees_paid_for_all_outcomes(p,price,expected_profit):
    result = calculate_net_value(D(p),D(price))
    assert result.expected_profit == D(expected_profit)
    assert result.net_ev == D(expected_profit)/result.total_cost


def test_zero_and_nonstandard_multiplier():
    free = calculate_net_value(D('.43'),D('.4'),FeePolicy(taker_multiplier=D(0)))
    assert free.entry_fee == 0
    assert free.net_ev == free.gross_ev
    double = calculate_net_value(D('.43'),D('.4'),FeePolicy(taker_multiplier=D(2)))
    assert double.entry_fee == D('.0336')
    assert double.net_ev < 0


@pytest.mark.parametrize('p,price', [(None,'.4'),('.5',None),('NaN','.4'),('.5','NaN'),('Infinity','.4'),('.5','Infinity'),('0','.4'),('1','.4'),('-.1','.4'),('1.1','.4'),('.5','0'),('.5','1'),('.5','-.1'),('.5','40')])
def test_invalid_values_not_rankable(p,price):
    assert calculate_net_value(D(p) if p is not None else None,D(price) if price is not None else None) is None


@pytest.mark.parametrize('changes', [dict(contracts=0),dict(contracts=-1),dict(contracts=True),dict(contracts=1.5),dict(taker_multiplier=D('-1')),dict(taker_multiplier=D('NaN')),dict(taker_multiplier=D('Infinity')),dict(balance_precision=D('.001'))])
def test_invalid_fee_policy_rejected(changes):
    with pytest.raises(ValueError): FeePolicy(**changes)


def item(ticker,p,price):
    return Opportunity(ticker,ticker,'YES',calculate_net_value(D(p),D(price)))


def test_net_ranking_reverses_gross_order_and_excludes_fee_losers():
    high_gross = item('A','.054','.05')  # 8% gross, 1.07% net.
    high_net = item('B','.53','.5')      # 6% gross, 2.42% net.
    fee_loser = item('C','.405','.4')
    breakeven = item('D','.4168','.4')
    assert high_gross.value.gross_ev > high_net.value.gross_ev
    assert fee_loser.value.gross_ev > 0 and fee_loser.value.net_ev < 0
    assert breakeven.value.net_ev == 0
    assert rank_opportunities([high_gross,fee_loser,breakeven,high_net]) == [high_net,high_gross]


def test_unrounded_sorting_and_stable_ties():
    lower = item('A','.53000001','.5')
    higher = item('Z','.53000002','.5')
    assert f'{lower.value.net_ev:.2%}' == f'{higher.value.net_ev:.2%}'
    assert rank_opportunities([lower,higher]) == [higher,lower]
    same = replace(lower,ticker='B')
    assert rank_opportunities([same,lower]) == [lower,same]


def test_independent_fraction_oracle_across_prices_and_sizes():
    def ceil_fraction(value,quantum):
        ratio=value/quantum
        return (-(-ratio.numerator//ratio.denominator))*quantum
    for precision in ['.0001','.01']:
        for contracts in [1,20,100]:
            for price in ['.01','.05505','.23','.4','.731','.99']:
                p,k=F('0.43'),F(price)
                cost=contracts*k
                model=F(7,100)*cost*(1-k)
                trade=ceil_fraction(model,F(1,1000000))
                total=ceil_fraction(cost+trade,F(precision))
                roi=(contracts*p-total)/total
                result=calculate_net_value(D('.43'),D(price),FeePolicy(contracts=contracts,balance_precision=D(precision)))
                assert F(result.entry_fee) == total-cost
                assert abs(result.net_ev-D(roi.numerator)/D(roi.denominator)) < D('1e-25')


def test_writer_and_terminal_share_ranking(tmp_path,monkeypatch):
    values=[item('A','.054','.05'),item('C','.405','.4'),item('B','.53','.5')]
    target=tmp_path/'opportunities.txt'
    monkeypatch.setattr(app,'OPPORTUNITIES_FILE',target)
    app._write_opportunities(values)
    assert target.read_text().splitlines()==app._ranked_opportunity_lines(values)
    lines=target.read_text().splitlines()
    assert lines[0].startswith('1. B') and lines[1].startswith('2. A')
    assert 'Net EV:' in lines[0] and 'Entry fee:' in lines[0] and 'Total cost:' in lines[0]
    app._write_opportunities([])
    assert target.read_text()==''


def prop_quote(side,odds):
    return SportsbookQuote('e','p','Player','receiving_yards','game',side,'ou',49.5,'book',odds)


def test_prop_no_probability_and_no_ask_used(capsys):
    quotes=[prop_quote('over',150),prop_quote('under',-150)]
    market=PlayerPropMarket('PROP','PROP-E','receiving_yards','Player',49.5,D('.01'),D('.5'),D('.02'),D('.4'))
    opportunities=[]
    app._print_prop_comparisons('NFL',quotes,[market],opportunities)
    assert len(opportunities)==1
    position=opportunities[0]
    assert position.side=='NO'
    assert position.value.fair_probability==D('.6')
    assert position.value.price==D('.4')
    assert position.value.entry_fee==D('.0168')
    assert position.value.net_ev==D('.1832')/D('.4168')
    output=capsys.readouterr().out
    assert 'net EV:' in output and 'gross EV:' in output


def test_moneyline_uses_yes_ask_and_fee_filtered():
    event=Event('e','NFL','Home Team','Away Team',datetime(2026,10,20,tzinfo=timezone.utc))
    quotes=[SportsbookQuote('e',None,None,'points','game',s,'ml',None,'book',o) for s,o in [('away',150),('home',-150)]]
    markets=[PredictionMarket(t,'E',title,D('.01'),ask,D('.02'),D('.03')) for t,title,ask in [('AWAY','Away wins',D('.395')),('HOME','Home wins',D('.5'))]]
    opportunities=[]
    app._print_moneyline_comparison(event,quotes,markets,opportunities)
    assert len(opportunities)==1 # Away gross-positive but net-negative.
    assert opportunities[0].ticker=='HOME' and opportunities[0].side=='YES'
    assert opportunities[0].value.price==D('.5')


def test_main_globally_ranks_moneylines_and_props(tmp_path,monkeypatch,capsys):
    policy=FeePolicy(contracts=20,balance_precision=D('.01'))
    settings=Settings('fake-key','America/Chicago','production','https://example.invalid','NFL',policy)
    events=[Event(str(i),'NFL','Home','Away',datetime(2026,10,20,tzinfo=timezone.utc)) for i in range(2)]
    monkeypatch.setattr(app,'load_settings',lambda:settings)
    monkeypatch.setattr(app,'get_todays_upcoming_events',lambda *a,**k:iter((e,{}) for e in events))
    monkeypatch.setattr(app,'get_open_markets',lambda *a,**k:iter([]))
    monkeypatch.setattr(app,'parse_sportsbook_quotes',lambda r:iter([]))
    monkeypatch.setattr(app,'find_potential_matches',lambda *a:[object()])
    monkeypatch.setattr(app,'kalshi_game_ticker_suffix',lambda *a:'GAME')
    monkeypatch.setattr(app,'get_player_prop_markets',lambda *a:iter([]))
    values=[item('A','.054','.05'),item('B','.53','.5')]
    def moneyline(event,quotes,matches,opportunities,fee_policy):
        assert fee_policy==policy
        opportunities.append(values[int(event.event_id)])
    def props(league,quotes,markets,opportunities,fee_policy):
        assert fee_policy==policy
        if not any(o.ticker=='Z' for o in opportunities):opportunities.append(item('Z','.7','.5'))
    monkeypatch.setattr(app,'_print_moneyline_comparison',moneyline)
    monkeypatch.setattr(app,'_print_prop_comparisons',props)
    target=tmp_path/'opportunities.txt'
    monkeypatch.setattr(app,'OPPORTUNITIES_FILE',target)
    app.main()
    lines=target.read_text().splitlines()
    assert [line.split()[1] for line in lines]==['Z','B','A']
    stdout=capsys.readouterr().out
    assert all(line in stdout for line in lines)
    assert '20 contract(s)' in stdout


def test_config_loads_fee_settings(monkeypatch):
    monkeypatch.setenv('SPORTS_GAME_ODDS_API_KEY','fake-key')
    monkeypatch.setenv('EV_CONTRACTS','20')
    monkeypatch.setenv('KALSHI_TAKER_FEE_MULTIPLIER','2')
    monkeypatch.setenv('KALSHI_BALANCE_PRECISION','0.01')
    assert load_settings().fee_policy == FeePolicy(20,D(2),D('.01'))


@pytest.mark.parametrize('name,value',[('EV_CONTRACTS','0'),('EV_CONTRACTS','1.5'),('KALSHI_TAKER_FEE_MULTIPLIER','NaN'),('KALSHI_TAKER_FEE_MULTIPLIER','bad'),('KALSHI_BALANCE_PRECISION','.1')])
def test_bad_config_fails_clearly(monkeypatch,name,value):
    monkeypatch.setenv('SPORTS_GAME_ODDS_API_KEY','fake-key')
    monkeypatch.setenv(name,value)
    with pytest.raises(RuntimeError,match='Invalid net-EV fee configuration'):load_settings()
