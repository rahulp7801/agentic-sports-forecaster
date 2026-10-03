"""Fixed side conversion and missing later asks remain in the denominator."""
from decimal import Decimal

from sportsbet.quant.kalshi_stat_only_prelock_prior20 import summarize


def test_no_side_uses_one_minus_strict_over_and_missing_stays_visible():
    selected = [
        {'ticker': 'NO', 'milestone_id': 'GAME1', 'side': 'no',
         'model_win_probability': .7},
        {'ticker': 'YES', 'milestone_id': 'GAME2', 'side': 'yes',
         'model_win_probability': .6},
        {'ticker': 'MISSING', 'milestone_id': 'GAME2', 'side': 'no',
         'model_win_probability': .8}]
    control = {'forecast_rows': [
        {'ticker': 'NO', 'prior20_over_probability': .2},
        {'ticker': 'YES', 'prior20_over_probability': .3},
        {'ticker': 'MISSING', 'prior20_over_probability': .1}]}
    observed = {'NO': ('prelock_exact_ask', Decimal('.6')),
                'YES': ('prelock_exact_ask', Decimal('.4')),
                'MISSING': ('batch_unavailable', None)}
    report = summarize(selected, control, observed)
    assert report['frozen_candidates'] == 3
    assert report['matched_later_asks'] == 2
    assert report['quote_states'] == {'batch_unavailable': 1,
                                      'prelock_exact_ask': 2}
    assert report['model_gross_margin_at_least_5pp'] == 2
    assert report['strict_prior20_gross_margin_at_least_5pp'] == 1
    assert report['mean_strict_prior20_side_probability'] == '0.55'
    assert not report['edge_established']
