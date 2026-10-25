"""Evidence-linked calendar/instant intervals; no dates inferred from prose."""
from __future__ import annotations

import calendar
import copy
from datetime import date, datetime, timezone
import json
import re

INSTANT = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})')


def boundary(value: dict) -> tuple[str, object, object]:
    precision, text = value['precision'], value['value']
    if precision == 'instant':
        if not INSTANT.fullmatch(text):
            raise ValueError('Instant bounds require a timezone and at most microsecond precision')
        try:
            instant = datetime.fromisoformat(text.upper().replace('Z', '+00:00')).astimezone(timezone.utc)
        except (ValueError, OverflowError) as exc:
            raise ValueError('Instant bound is outside the supported calendar/offset range') from exc
        return 'instant', instant, instant
    patterns = {'year': r'[0-9]{4}', 'month': r'[0-9]{4}-[0-9]{2}', 'day': r'[0-9]{4}-[0-9]{2}-[0-9]{2}'}
    if precision not in patterns or not re.fullmatch(patterns[precision], text):
        raise ValueError('Calendar value does not match its declared precision')
    parts = list(map(int, text.split('-')))
    year = parts[0]
    if precision == 'year':
        first, last = date(year, 1, 1), date(year, 12, 31)
    elif precision == 'month':
        month = parts[1]
        first, last = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    else:
        first = last = date(*parts)
    return 'calendar', first.toordinal(), last.toordinal()


def validate_temporal(value: dict, evidence_ids: list[str]) -> None:
    """Schema supplies types; this checks calendar/order and actual evidence scope."""
    status, intervals = value['status'], value['intervals']
    if status == 'unknown' and intervals:
        raise ValueError('Unknown valid time must not assert intervals')
    if status != 'unknown' and not intervals:
        raise ValueError('Specified/disputed valid time needs evidence-backed intervals')
    if status == 'disputed' and len(intervals) < 2:
        raise ValueError('Disputed valid time needs at least two recorded alternatives')
    if status in ('unknown', 'disputed') and not value['notes']:
        raise ValueError('Unknown/disputed valid time needs an explicit explanation')
    scopes = set()
    for interval in intervals:
        scope = json.dumps({key: item for key, item in interval.items() if key != 'evidence_ids'}, sort_keys=True)
        if scope in scopes:
            raise ValueError('Duplicate temporal scope; combine its evidence instead')
        scopes.add(scope)
        if not set(interval['evidence_ids']) <= set(evidence_ids):
            raise ValueError('Temporal evidence must be linked to the same claim')
        start = boundary(interval['start']) if interval['start'] is not None else None
        end = boundary(interval['end']) if interval['end'] is not None else None
        if start and end:
            if start[0] != end[0]:
                raise ValueError('Do not mix calendar and instant bounds without an explicit conversion')
            if start[1] > end[2] or (start[1] == end[2] and not
                    (interval['start_inclusive'] and interval['end_inclusive'])):
                raise ValueError('Temporal interval is reversed or necessarily empty')


def temporal_scope(value: dict | None) -> str:
    """Scope identity excludes evidential additions and editorial limitation notes."""
    if value is None:
        return json.dumps({'status': 'unknown', 'intervals': []}, sort_keys=True)
    intervals = [{key: item for key, item in interval.items() if key != 'evidence_ids'}
                 for interval in value['intervals']]
    intervals.sort(key=lambda interval: json.dumps(interval, sort_keys=True))
    return json.dumps({'status': value['status'], 'intervals': intervals}, sort_keys=True)


def merge_temporal(previous: dict | None, incoming: dict) -> dict:
    if previous is None:
        return copy.deepcopy(incoming)
    if temporal_scope(previous) != temporal_scope(incoming):
        raise ValueError('Temporal scope differs; do not rewrite a claim ID with another proposition')
    result = copy.deepcopy(previous)
    result['notes'] = sorted(set(previous['notes']) | set(incoming['notes']))
    key = lambda interval: json.dumps({name: item for name, item in interval.items()
                                       if name != 'evidence_ids'}, sort_keys=True)
    by_scope = {key(interval): interval for interval in result['intervals']}
    for interval in incoming['intervals']:
        target = by_scope[key(interval)]
        target['evidence_ids'] = sorted(set(target['evidence_ids']) | set(interval['evidence_ids']))
    return result


def point(text: str) -> tuple[str, object]:
    kind, first, _ = boundary({'precision': 'day' if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', text)
                               else 'instant', 'value': text})
    return kind, first


def applicability(value: dict | None, at: tuple[str, object]) -> tuple[str, str]:
    if value is None:
        return 'unresolved', 'not_recorded'
    if value['status'] != 'specified':
        return 'unresolved', value['status']
    uncertain = False
    for interval in value['intervals']:
        start = boundary(interval['start']) if interval['start'] is not None else None
        end = boundary(interval['end']) if interval['end'] is not None else None
        kind, query = at
        if any(bound is not None and bound[0] != kind for bound in (start, end)):
            uncertain = True
            continue
        after_start = start is None or query > start[2] or (query == start[2] and interval['start_inclusive'])
        before_end = end is None or query < end[1] or (query == end[1] and interval['end_inclusive'])
        before_start = start is not None and (query < start[1] or (query == start[1] and not interval['start_inclusive']))
        after_end = end is not None and (query > end[2] or (query == end[2] and not interval['end_inclusive']))
        if after_start and before_end:
            return 'matches', 'recorded_interval_covers_query'
        if not (before_start or after_end):
            uncertain = True
    return ('unresolved', 'partial_precision_or_calendar_instant_mismatch') if uncertain else ('outside', 'outside_recorded_intervals')
