"""Decision-time guards shared by scanner admission and exposure reservation."""
from datetime import datetime


def admission_timing_reason(now: datetime, *, game_start_time: datetime,
                            quote_time: datetime, availability_time: datetime | None) -> str | None:
    values=(now,game_start_time,quote_time)+((availability_time,) if availability_time is not None else ())
    if any(not isinstance(value,datetime) or value.utcoffset() is None for value in values):
        raise ValueError('Admission timing requires aware timestamps')
    if now >= game_start_time:
        return 'game_started'
    if not -60 <= (now-quote_time).total_seconds() <= 300:
        return 'stale_quote'
    if availability_time is None or not -60 <= (now-availability_time).total_seconds() <= 3600:
        return 'availability_unavailable'
    return None
