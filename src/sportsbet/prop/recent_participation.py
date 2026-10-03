"""Dated descriptive participation subsets; model and eligibility are unchanged."""
from datetime import date, timedelta
import math

VERSION = 'participation-recent-30d-v1'


def recent_participation(cohorts, cutoff, line, direction):
    """Summarize only proved retrieved games in [cutoff-30 days, cutoff)."""
    if (type(cutoff) is not date or direction not in ('over', 'under')
            or type(line) not in (int, float) or not math.isfinite(line)
            or set(cohorts) != {'active', 'absent', 'unknown'}
            or sum(len(rows) for rows in cohorts.values()) > 40):
        raise ValueError('Invalid recent participation scope')
    since = cutoff - timedelta(days=30)
    groups = {}
    for group, rows in cohorts.items():
        for day, value in rows:
            if (type(day) is not date or day >= cutoff
                    or type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError('Recent participation requires prior observed values')
        groups[group] = [(day, value) for day, value in rows if day >= since]

    def summary(group):
        values = [value for _, value in groups[group]]
        hits = sum(value > line if direction == 'over' else value < line for value in values)
        return dict(games=len(values), mean=round(sum(values)/len(values), 2) if values else None,
                    hit_rate=round(hits/len(values), 4) if values else None)

    window = {'cutoff': cutoff.isoformat()}
    for group, rows in groups.items():
        window[group] = dict(oldest=min(day for day, _ in rows).isoformat(),
                            newest=max(day for day, _ in rows).isoformat()) if rows else None
    return dict(version=VERSION, since=since.isoformat(), cutoff=cutoff.isoformat(),
                active=summary('active'), absent=summary('absent'),
                unknown_games=len(groups['unknown']), sample_window=window)
