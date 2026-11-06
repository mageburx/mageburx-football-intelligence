"""Conservative football status rules: a numeric score does not mean full time."""
from __future__ import annotations
import datetime as dt

FINAL_STATUSES=frozenset({'FT','AET','PEN','FULL TIME','FULLTIME','MATCH FINISHED','FINISHED','AFTER EXTRA TIME','AFTER PENALTIES'})
LIVE_STATUSES=frozenset({'1H','HT','2H','ET','BT','P','PT','LIVE','IN PLAY','IN PROGRESS','HALF TIME','HALFTIME'})

def normalize_status(value):
    return ' '.join(str(value or '').upper().strip().replace('_',' ').split())

def final_confirmed(raw, now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None: raise ValueError('UTC timestamp required')
    now=now.astimezone(dt.timezone.utc)
    if normalize_status(raw.get('strStatus')) not in FINAL_STATUSES: return False
    try:
        if any(type(raw.get(k)) is bool or not 0<=int(raw[k])<100 for k in ('intHomeScore','intAwayScore')): return False
    except (ValueError,TypeError,KeyError): return False
    stamp=str(raw.get('strTimestamp') or '').strip()
    if stamp:
        try:
            start=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if start.tzinfo is None: start=start.replace(tzinfo=dt.timezone.utc)
            return now-start.astimezone(dt.timezone.utc)>=dt.timedelta(minutes=80)
        except ValueError: return False
    try: return dt.date.fromisoformat(str(raw.get('dateEvent'))) < now.date()
    except (ValueError,TypeError): return False

def verified_event(event):
    return (isinstance(event,dict) and event.get('result_verified') is True
            and event.get('finished') is True
            and normalize_status(event.get('match_status')) in FINAL_STATUSES
            and type(event.get('home_score')) is int and type(event.get('away_score')) is int
            and event['home_score']>=0 and event['away_score']>=0)
