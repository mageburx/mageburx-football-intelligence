#!/usr/bin/env python3
"""Read future fixtures from the same official public DBU match-program table.

This parser only accepts announced matches from the official *single* league
table already fetched after a successful robots.txt check; it never treats
unscored past games as future or invents kickoff times.
"""
from __future__ import annotations
import datetime as dt
import re
from zoneinfo import ZoneInfo

try:
    from scripts.scrape_dbu import TableRows
except ModuleNotFoundError:
    from scrape_dbu import TableRows

MATCH_NUMBER=re.compile(r'\d{6,8}')
DATE_PATTERN=re.compile(r'\b(\d{2})-(\d{2})\s+(20\d{2})\b')
HOUR_PATTERN=re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d')
TIMEZONE=ZoneInfo('Europe/Copenhagen')


def future_schedule(html,now,normalize):
    if now.tzinfo is None:raise ValueError('Expected timezone aware date')
    if 'Kampnr' not in html and 'Kampprogram' not in html:
        raise ValueError('Unrecognized DBU match program')
    rows=TableRows()
    rows.feed(html)
    today=now.astimezone(TIMEZONE).date()
    future=[]
    seen=set()
    unknown=set()
    for row in rows.rows:
        match_id=next((x for x in row if MATCH_NUMBER.fullmatch(x)),None)
        if not match_id:continue
        date_i=next((i for i,v in enumerate(row) if DATE_PATTERN.search(v)),None)
        if date_i is None or len(row)<=date_i+3:continue
        date_text=DATE_PATTERN.search(row[date_i])
        try:
            date=dt.date(int(date_text.group(3)),int(date_text.group(2)),
                         int(date_text.group(1)))
        except (ValueError,TypeError):continue
        if not(dt.date(2026,7,1)<=date<=dt.date(2027,6,30)) or date<=today:
            continue
        try:
            home,away=normalize(row[date_i+2]),normalize(row[date_i+3])
        except ValueError as exc:
            unknown.add(str(exc)[:90])
            continue
        if not home or not away or home==away:continue
        if match_id in seen:
            raise ValueError('Duplicate official DBU match number '+match_id)
        seen.add(match_id)
        raw_time=row[date_i+1].strip()
        hour=raw_time if HOUR_PATTERN.fullmatch(raw_time) else None
        if hour:
            hour_i,minute_i=map(int,hour.split(':'))
            start=dt.datetime.combine(date,dt.time(hour_i,minute_i),
                                     tzinfo=TIMEZONE).astimezone(dt.timezone.utc)
            utc=start.isoformat().replace('+00:00','Z')
        else:
            utc=''
        future.append({
            'id':'dbu:'+match_id,
            'dbu_match_id':match_id,
            'date':date.isoformat(),
            'utc':utc,'round':0,'home':home,'away':away,
            'home_score':None,'away_score':None,'finished':False,
            'source':'DBU official Betinia Liga schedule',
            'kickoff_time_confirmed':hour is not None,
        })
    return future,sorted(unknown)
