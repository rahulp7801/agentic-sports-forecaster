from datetime import datetime, timezone
import pytest
from sportsbet.ledger import Ledger,quote_evidence_valid
from sportsbet.model_contract import CFB_MODEL_VERSION,CFB_HISTORY_POLICY
from sportsbet.quant import cfb_history_edge as audit, multisport_edge as original
from tests.test_multisport_edge import forecast

NOW=datetime(2026,9,29,5,tzinfo=timezone.utc)


def new_forecast(**changes):
    return forecast('cfb','2026-09-29T04:15:00+00:00',
        game_date='2026-09-29',game_start_time='2026-09-30T00:00:00+00:00',
        model_version=CFB_MODEL_VERSION,history_policy_version=CFB_HISTORY_POLICY,**changes)


def test_new_cohort_does_not_mix_or_mutate_frozen_baseline(tmp_path):
    ledger=Ledger(tmp_path/'audit.sqlite')
    ledger.record('old',forecast('cfb'))
    before=original.audit_sport(ledger,'cfb',now=NOW)
    ledger.record('new',new_forecast())
    assert original.audit_sport(ledger,'cfb',now=NOW)==before
    result=audit.audit_sport(ledger,'cfb',now=NOW)
    assert result['status']=='insufficient_data' and result['promote'] is False
    assert result['cohorts']['all_predictions']['earliest_selections']==1
    assert result['cohorts']['recommendations']['pending']==1
    assert audit.PROTOCOL['minimum_paired_games']==50


@pytest.mark.parametrize('changes', [dict(history_policy_version=None),dict(history_policy_version='other'),
    dict(sport='nfl'),dict(model_generated_at='2026-09-29T04:14:59+00:00'),
    dict(model_generated_at='2026-09-29T04:16:00+00:00')])
def test_new_model_requires_exact_policy_sport_and_generation_window(changes):
    p=new_forecast()
    assert quote_evidence_valid(p)
    assert not quote_evidence_valid(p | changes)
