#!/usr/bin/env python3
"""Read and verify Resolvent workflow references; never execute them or write files."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from urllib.request import HTTPRedirectHandler, Request, build_opener

SOURCE = 'https://raw.githubusercontent.com/autonomio/resolvent/'
INDEX_URL = SOURCE + 'workflow-release/workflow.json'
PREFIX = 'workflows/resolvent/'
MAX_INDEX = 65536
MAX_FILE = 262144
MAX_TOTAL = 1048576
CLIENT_PROTOCOL = '1.0'


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError('Expected a canonical workflow version')
    return tuple(map(int, value.split('.')))


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate manifest member: ' + key)
        result[key] = value
    return result


def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def safe_path(path):
    if (not isinstance(path, str) or len(path) > 200 or
            not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*\.(?:md|json)', path) or
            any(part in ('.', '..') for part in path.split('/'))):
        raise ValueError('Unsafe workflow path')


def validate_manifest(value):
    expected = {'format_version', 'client_protocol', 'workflow_version', 'source_commit', 'entrypoint', 'files'}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError('Unexpected workflow manifest fields')
    if value['format_version'] != '1.0' or value['client_protocol'] != CLIENT_PROTOCOL:
        raise ValueError('Incompatible workflow/client protocol; update the installed plugin')
    version(value['workflow_version'])
    if not isinstance(value['source_commit'], str) or not re.fullmatch('[0-9a-f]{40}', value['source_commit']):
        raise ValueError('Workflow source must be a full commit SHA')
    files = value['files']
    if not isinstance(files, dict) or not 1 <= len(files) <= 32:
        raise ValueError('Invalid workflow file inventory')
    total = 0
    for path, record in files.items():
        safe_path(path)
        if not isinstance(record, dict) or set(record) != {'sha256', 'git_blob_sha1', 'size'}:
            raise ValueError('Invalid workflow file metadata')
        for key, length in (('sha256', 64), ('git_blob_sha1', 40)):
            if not isinstance(record[key], str) or not re.fullmatch('[0-9a-f]{' + str(length) + '}', record[key]):
                raise ValueError('Invalid workflow digest')
        if type(record['size']) is not int or not 0 < record['size'] <= MAX_FILE:
            raise ValueError('Invalid workflow file size')
        total += record['size']
    if total > MAX_TOTAL:
        raise ValueError('Workflow exceeds total size limit')
    if not isinstance(value['entrypoint'], str) or value['entrypoint'] not in files or not value['entrypoint'].endswith('.md'):
        raise ValueError('Missing workflow entrypoint')
    return value


def parse_manifest(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_INDEX:
        raise ValueError('Invalid workflow manifest size')
    return validate_manifest(json.loads(data.decode('utf-8'), object_pairs_hook=object_pairs))


def file_url(manifest, path):
    validate_manifest(manifest)
    if path not in manifest['files']:
        raise ValueError('File is not in the workflow manifest')
    return SOURCE + manifest['source_commit'] + '/' + PREFIX + path


def verify_file(manifest, path, data):
    file_url(manifest, path)
    record = manifest['files'][path]
    if (not isinstance(data, bytes) or len(data) != record['size'] or
            hashlib.sha256(data).hexdigest() != record['sha256'] or blob_sha(data) != record['git_blob_sha1']):
        raise ValueError('Workflow content does not match its manifest: ' + path)
    return data.decode('utf-8')


def verify_connector_metadata(manifest, path, entry):
    """The no-shell route uses GitHub's pinned tree/blob identity, never prose hashes."""
    file_url(manifest, path)
    expected = manifest['files'][path]
    if (entry.get('type') != 'blob' or entry.get('mode') != '100644' or
            entry.get('sha') != expected['git_blob_sha1'] or type(entry.get('size')) is not int or
            entry['size'] != expected['size']):
        raise ValueError('GitHub object metadata does not match workflow manifest: ' + path)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Workflow redirects are not permitted')


def fetch(url, limit):
    # No cookies, authentication, chat content, configurable origin or redirected requests.
    request = Request(url, headers={'User-Agent': 'Resolvent-workflow/1.0'})
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Workflow response exceeds size limit')
    return data


def load(reader=fetch):
    manifest = parse_manifest(reader(INDEX_URL, MAX_INDEX))
    files = {}
    for path, record in sorted(manifest['files'].items()):
        files[path] = verify_file(manifest, path, reader(file_url(manifest, path), record['size']))
    return {'manifest': manifest, 'files': files}


if __name__ == '__main__':
    try:
        print(json.dumps(load(), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        sys.exit('Workflow not loaded: ' + str(error))
