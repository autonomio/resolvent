#!/usr/bin/env python3
"""Send one actionable ChatGPT publisher notice per available plugin release."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY = 'autonomio/resolvent'
RECEIPT = 'chatgpt-notification.json'
UPDATE_URL = 'https://platform.openai.com/plugins'
# Resend retains idempotency keys for 24 hours. Stop before that window expires
# if acceptance could not be recorded; an operator must inspect Resend first.
RETRY_WINDOW = timedelta(hours=23)


def message(release: dict, update_url: str) -> dict:
    tag = release.get('tag_name', '')
    match = re.fullmatch(r'resolvent-v((0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*))', tag)
    if not match or not release.get('published_at') or release.get('prerelease'):
        raise ValueError('Notice requires an available stable plugin release')
    version = match[1]
    name = f'resolvent-chatgpt-{version}.zip'
    download = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
    asset = next((a for a in release.get('assets', []) if a.get('name') == name), None)
    if not asset or asset.get('browser_download_url') != download or asset.get('size', 0) <= 0:
        raise ValueError('Published ChatGPT ZIP is missing or has an unexpected URL')
    release_url = f'https://github.com/{REPOSITORY}/releases/tag/{tag}'
    if release.get('html_url') != release_url:
        raise ValueError('Unexpected release URL')
    if update_url != UPDATE_URL and not re.fullmatch(re.escape(UPDATE_URL) + r'/[A-Za-z0-9/_-]+', update_url):
        raise ValueError('Update URL must point to the official ChatGPT plugin publisher portal')
    return {
        'subject': f'Resolvent {version}: ChatGPT plugin update ready',
        'text': (
            f'Resolvent {version} by Autonomio is available.\n\n'
            'The bundled plugin changed. Update the Resolvent listing in ChatGPT:\n\n'
            f'Download the new ZIP: {download}\n'
            f'Open the plugin publisher portal: {update_url}\n'
            f'Release and checksums: {release_url}\n\n'
            'Upload the ZIP to Resolvent, complete the required checks and review, '
            'then publish the update. GitHub release publication does not update '
            'the ChatGPT listing automatically.\n'
        ),
    }


def send_resend(payload: dict, key: str, idempotency_key: str) -> str:
    request = Request('https://api.resend.com/emails',
                      data=json.dumps(payload).encode(), method='POST', headers={
                          'Authorization': 'Bearer ' + key,
                          'Content-Type': 'application/json',
                          'Idempotency-Key': idempotency_key,
                      })
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as error:
        raise ValueError(f'Resend rejected the notice (HTTP {error.code}); inspect the provider before retrying') from None
    except (URLError, TimeoutError):
        raise ValueError('Resend outcome is uncertain; retry within 23 hours or inspect the provider') from None
    provider_id = result.get('id')
    if not isinstance(provider_id, str) or not provider_id:
        raise ValueError('Resend acceptance did not include a message ID')
    return provider_id


def notify(release: dict, receipt: dict | None, config: dict, persist, send=send_resend,
           now: datetime | None = None) -> bool:
    content = message(release, config.get('CHATGPT_PLUGIN_UPDATE_URL') or UPDATE_URL)
    tag = release['tag_name']
    if receipt:
        if receipt.get('tag') != tag or receipt.get('status') not in ('pending', 'accepted'):
            raise ValueError('Invalid notification receipt; inspect it before retrying')
        if receipt['status'] == 'accepted':
            if not receipt.get('provider_id'):
                raise ValueError('Notification receipt has no provider acceptance ID')
            return False
    key = config.get('RESEND_API_KEY')
    recipient = config.get('RESOLVENT_NOTIFY_TO')
    sender = config.get('RESOLVENT_NOTIFY_FROM')
    if not key or not recipient or not sender:
        raise ValueError('Configure RESEND_API_KEY, RESOLVENT_NOTIFY_TO and RESOLVENT_NOTIFY_FROM')
    payload = {'from': sender, 'to': [recipient], **content}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    now = now or datetime.now(timezone.utc)
    if receipt:
        attempted = datetime.fromisoformat(receipt['attempted_at'])
        if attempted.tzinfo is None or not timedelta(0) <= now - attempted < RETRY_WINDOW:
            raise ValueError('Pending notice exceeds the safe retry window; inspect Resend before retrying')
        if receipt.get('payload_sha256') != digest:
            raise ValueError('Pending notice payload changed; inspect Resend before retrying')
        intent = receipt
    else:
        intent = {'tag': tag, 'status': 'pending', 'attempted_at': now.isoformat(), 'payload_sha256': digest}
        # A durable intent must exist before an external send can occur.
        persist(intent)
    provider_id = send(payload, key, f'{REPOSITORY}/chatgpt-update/{tag}')
    persist({**intent, 'status': 'accepted', 'provider_id': provider_id})
    return True


def github(*args: str) -> str:
    result = subprocess.run(['gh', *args], text=True, capture_output=True)
    if result.returncode:
        raise ValueError('GitHub release notification journal operation failed')
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'resolvent-v[0-9]+\.[0-9]+\.[0-9]+', args.tag):
        parser.error('Invalid plugin release tag')
    try:
        release = json.loads(github('api', f'repos/{REPOSITORY}/releases/tags/{args.tag}'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / RECEIPT
            receipt = None
            if any(asset.get('name') == RECEIPT for asset in release.get('assets', [])):
                github('release', 'download', args.tag, '--repo', REPOSITORY,
                       '--pattern', RECEIPT, '--dir', directory)
                receipt = json.loads(path.read_text())

            def persist(record):
                path.write_text(json.dumps(record, indent=2) + '\n')
                github('release', 'upload', args.tag, str(path), '--repo', REPOSITORY, '--clobber')

            sent = notify(release, receipt, os.environ, persist)
            print('ChatGPT update notice accepted by Resend' if sent else 'ChatGPT update notice already accepted; skipped')
    except (ValueError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
