"""Untrusted change-signal validation and identity; no fetching or world mutations."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
import re
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

TIME_PATTERN = r'^\d{4}-\d{2}-\d{2}[Tt](?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)$'


def metadata_instant(value):
    if not isinstance(value,str) or not re.fullmatch(TIME_PATTERN,value):
        raise ValueError('Signal metadata requires a full timezone-qualified timestamp')
    try:
        return datetime.fromisoformat(value.replace('t','T').replace('z','Z').replace('Z','+00:00'))
    except ValueError as error:
        raise ValueError('Invalid signal metadata calendar/timestamp') from error


def validate_signal(signal: dict, policy_root: Path):
    if not isinstance(signal, dict):
        raise ValueError('Change signal must be an object')
    try:
        encoded = json.dumps(signal, ensure_ascii=False, sort_keys=True,allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError('Malformed change-signal data') from error
    if len(encoded) > 65536:
        raise ValueError('Change signal exceeds 64 KiB')
    schema = json.loads((policy_root/'docs/schemas/change-signal.schema.json').read_text())
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(signal))
    if errors:
        # Do not echo invalid or potentially sensitive payload values into runner logs.
        raise ValueError('Invalid change-signal contract: ' + str(errors[0].validator))
    metadata_instant(signal['observed_at'])
    reference = urlsplit(signal['reference'])
    if reference.scheme in ('http','https') and (reference.username or reference.password):
        raise ValueError('Credential-bearing change-signal references are not accepted')
    return signal


def signal_id(signal: dict) -> str:
    # Observation time and commentary do not turn a replay into a new upstream version.
    fields = ('schema_version','event_type','origin','reference','revision','fingerprint')
    identity = {key:signal[key] for key in fields}
    identity['affected_ids'] = sorted(signal['affected_ids'])
    if 'before_revision' in signal:
        identity['before_revision'] = signal['before_revision']
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',',':')).encode('utf-8')
    return 'CS-' + hashlib.sha256(raw).hexdigest()
