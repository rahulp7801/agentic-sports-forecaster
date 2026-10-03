"""Offline, outcome-blind context cross-check of the fixed eight NFL paper decisions."""
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant import kalshi_stat_only_receptions_no_tail as tail
from sportsbet.quant import kalshi_stat_only_teammate_context as context
from sportsbet.quant.kalshi_market_cohort import clock, digest

LOCAL = Path('.local')
CONTEXT_FILE_SHA256 = '733dc3f4a1b4d5fc85aeb32ce5f8117d264976e33a1f51933da883735484c792'
receipt_path = LOCAL / 'kalshi-stat-only-teammate-context-pre-result-20261004.json'
raw = receipt_path.read_bytes()
if hashlib.sha256(raw).hexdigest() != CONTEXT_FILE_SHA256:
    raise ValueError('Pregame context file changed')
receipt = json.loads(raw)
if (receipt.get('record_sha256') != context.EXPECTED_RECORD_SHA256
        or digest({k: v for k, v in receipt.items() if k != 'record_sha256'})
        != context.EXPECTED_RECORD_SHA256
        or not clock(receipt['recorded_at']) < clock(receipt['first_kickoff_at'])):
    raise ValueError('Pregame context integrity or timing failed')
forecast = frozen._pinned(LOCAL / 'kalshi-stat-only-probabilities-20261004.json', 'forecast')
decisions = frozen._pinned(LOCAL / 'kalshi-stat-only-ask-decisions-20261004.json', 'decisions')
selected = tail.selected_rows(forecast, decisions)
sizes = [Decimal(str(row['displayed_size'])) for row in selected]
ages = [(clock(decisions['decided_at']) - clock(row['price_received_at'])).total_seconds()
        for row in selected]
margins = [Decimal(str(row['gross_margin'])) for row in selected]
if (any(size <= 0 for size in sizes) or any(not 0 <= age <= 300 for age in ages)
        or any(margin < Decimal('0.05') for margin in margins)):
    raise ValueError('Frozen ask depth, timing or margin failed')
context_rows = receipt['rows']
if (len(context_rows) != 70 or len({row['ticker'] for row in context_rows}) != 70
        or {row['ticker'] for row in context_rows}
        != {row['ticker'] for row in decisions['candidates']}):
    raise ValueError('Original context or decision denominator changed')
by_ticker = {row['ticker']: row for row in context_rows}
joined = []
for decision in selected:
    row = by_ticker[decision['ticker']]
    if (row['high_probability'] is not True or row['side'] != decision['side']
            or row['milestone_id'] != decision['milestone_id']
            or Decimal(str(row['model_win_probability']))
            != Decimal(str(decision['model_win_probability']))
            or Decimal(str(row['displayed_ask']))
            != Decimal(str(decision['displayed_ask']))):
        raise ValueError('Pregame context mismatches frozen decision')
    joined.append(row)
report = dict(
    protocol='kalshi-nfl-stat-only-receptions-context-crosscheck-v1',
    context_record_sha256=context.EXPECTED_RECORD_SHA256,
    selected_tickers_sha256=tail.EXPECTED_TICKERS_SHA256,
    original_paper_candidates=len(context_rows),
    fixed_receptions_candidates=len(joined),
    fixed_receptions_games=len({row['milestone_id'] for row in joined}),
    teammate_context_strata=dict(sorted(Counter(
        row['teammate_context_stratum'] for row in joined).items())),
    subject_report_status=dict(sorted(Counter(
        row['subject_report_status'] for row in joined).items())),
    acute_qb_teammate_count=sum(bool(row['acute_qb_teammate']) for row in joined),
    min_displayed_size=str(min(sizes)),
    max_displayed_size=str(max(sizes)),
    min_quote_age_seconds=round(min(ages), 2),
    max_quote_age_seconds=round(max(ages), 2),
    min_arithmetic_gross_margin=str(min(margins)),
    max_arithmetic_gross_margin=str(max(margins)),
    outcome_observed=False,
    edge_established=False,
)
print(json.dumps(report, sort_keys=True, indent=2))
