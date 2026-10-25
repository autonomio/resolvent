#!/usr/bin/env python3
"""Read pinned compiled knowledge with bounded, provenance-preserving queries."""
from __future__ import annotations

import argparse
from collections import Counter, deque
import copy
import json
from pathlib import Path
import re
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.build_knowledge import ROOT, json_bytes, projection, sha256
from scripts.model import CANONICAL_ROOTS, Invalid, digest, family, safe_relative, unique_pairs, validate_state


def read_json(contents: bytes) -> dict:
    value = json.loads(contents, object_pairs_hook=unique_pairs,
                       parse_constant=lambda value: (_ for _ in ()).throw(Invalid(f'Non-finite number: {value}')))
    if not isinstance(value, dict):
        raise Invalid('Expected a package object')
    return value


def bound(value: int, low: int, high: int, name: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise Invalid(f'{name} must be between {low} and {high}')


def page(items: list, limit: int, offset: int = 0) -> dict:
    return {'items': copy.deepcopy(items[offset:offset + limit]), 'total': len(items),
            'offset': offset, 'next_offset': offset + limit if offset + limit < len(items) else None}


def tokens(text: str) -> list[str]:
    return re.findall(r'\w+', text.casefold())


class Knowledge:
    def __init__(self, package: Path, manifest_sha256: str | None = None):
        for name in ('manifest.json', 'knowledge.json'):
            if (package / name).is_symlink():
                raise Invalid('Package files must be regular files')
        manifest_bytes = (package / 'manifest.json').read_bytes()
        manifest_hash = sha256(manifest_bytes)
        if manifest_sha256 is not None and manifest_hash != manifest_sha256:
            raise Invalid('Pinned manifest hash does not match this build')
        manifest = read_json(manifest_bytes)
        if (manifest['artifact_format'] != 'resolvent.knowledge' or
                manifest['artifact_format_version'] != '1.0' or manifest['schema_version'] != '1.0' or
                manifest['derived'] is not True):
            raise Invalid('Unsupported compiled package format')
        if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', manifest['source_revision']):
            raise Invalid('Package revision must be a full Git commit ID')
        knowledge_bytes = (package / 'knowledge.json').read_bytes()
        integrity = manifest['artifacts']['knowledge.json']
        if sha256(knowledge_bytes) != integrity['sha256'] or len(knowledge_bytes) != integrity['bytes']:
            raise Invalid('Knowledge artifact integrity check failed')
        self.knowledge = read_json(knowledge_bytes)
        self.records = self.knowledge['records']
        if set(self.records) != set(CANONICAL_ROOTS):
            raise Invalid('Unexpected canonical projection groups')
        state = {}
        for group, records in self.records.items():
            for record_id, record in records.items():
                if record_id != record['id']:
                    raise Invalid('Projection key differs from record ID')
                state[f'{group}/{record_id}.yaml'] = record
        for path, record in self.knowledge['provenance'].items():
            if not safe_relative(path) or family(path) in CANONICAL_ROOTS or path in state:
                raise Invalid('Invalid provenance path')
            state[path] = record
        counts = validate_state(state, ROOT, require_closure=True)
        if projection(state) != self.knowledge:
            raise Invalid('Compiled projection or reverse links disagree with canonical records')
        if (set(manifest['input_files']) != set(state) or
                digest(manifest['input_files']) != manifest['input_tree_sha256'] or
                any(not re.fullmatch(r'[0-9a-f]{64}', value) for value in manifest['input_files'].values())):
            raise Invalid('Input-tree manifest is inconsistent')
        validation = manifest['validation']
        if (validation['structural_validation'] != 'passed' or validation['require_closure'] is not True or
                validation['records'] != counts):
            raise Invalid('Package does not record closed structural validation')
        self.build = {'source_revision': manifest['source_revision'], 'manifest_sha256': manifest_hash,
                       'input_tree_sha256': manifest['input_tree_sha256']}
        self.by_id = {record_id: (group, record) for group, records in self.records.items()
                       for record_id, record in records.items()}
        self.rebuild_index()

    def rebuild_index(self) -> None:
        """Replace an in-memory keyword index without changing records or package bytes."""
        self.documents = {}
        for cid, claim in self.records['claims'].items():
            texts = {cid: claim['statement']}
            for eid in claim['evidence_ids']:
                evidence = self.records['evidence'][eid]
                texts[eid] = evidence['summary'] + ' ' + ' '.join(evidence['limitations'])
                for sid in evidence['source_ids']:
                    source = self.records['sources'][sid]
                    texts[sid] = ' '.join(source[key] or '' for key in ('title', 'uri', 'date', 'locator', 'excerpt'))
            self.documents[cid] = {record_id: Counter(tokens(text)) for record_id, text in texts.items()}

    def envelope(self, operation: str, **result) -> dict:
        return {'format_version': '1.0', 'build': dict(self.build), 'operation': operation, **result}

    def relevant(self, record_id: str) -> tuple[dict, dict]:
        group, record = self.by_id[record_id]
        ids = {name: set() for name in CANONICAL_ROOTS}
        ids[group].add(record_id)
        if group == 'claims':
            ids['evidence'].update(record['evidence_ids'])
            reverse = self.knowledge['reverse_links']['claims'][record_id]
            ids['graph'].update(reverse['incoming_connector_ids'] + reverse['outgoing_connector_ids'])
        elif group == 'evidence':
            ids['claims'].update(record['claim_ids'])
            ids['graph'].update(self.knowledge['reverse_links']['evidence'][record_id]['connector_ids'])
        elif group == 'sources':
            ids['evidence'].update(self.knowledge['reverse_links']['sources'][record_id]['evidence_ids'])
        elif group == 'graph':
            ids['claims'].update([record['from'], record['to']])
        elif group == 'questions':
            ids['claims'].update(record['claim_ids'])
        for connector_id in ids['graph']:
            connector = self.records['graph'][connector_id]
            ids['claims'].update([connector['from'], connector['to']])
            ids['evidence'].update(connector['evidence_ids'])
        for eid in ids['evidence']:
            evidence = self.records['evidence'][eid]
            ids['sources'].update(evidence['source_ids'])
            ids['claims'].update(evidence['claim_ids'])
        for cid in ids['claims']:
            ids['questions'].update(self.knowledge['reverse_links']['claims'][cid]['question_ids'])
        paths = {f'{kind}/{item_id}.yaml' for kind, values in ids.items() for item_id in values}
        provenance = self.knowledge['provenance']
        selected, runs = {}, set()
        for path, item in provenance.items():
            kind = family(path)
            if ((kind == 'closure' and paths.intersection(item['touched_files'])) or
                    (kind == 'maintenance' and (paths.intersection(item['touched_files']) or
                                               ids['claims'].intersection(item['claim_ids'])))):
                selected[path] = item
                if kind == 'closure':
                    runs.add(item['submission_id'])
        submissions = {item['id']: item for path, item in provenance.items() if family(path) == 'submission'}
        pending = list(runs)
        while pending:
            parent = submissions[pending.pop()]['parent_run_id']
            if parent is not None and parent not in runs:
                runs.add(parent)
                pending.append(parent)
        for path, item in provenance.items():
            if item.get('submission_id') in runs or (family(path) == 'submission' and item['id'] in runs):
                selected[path] = item
        return ids, selected

    def view(self, record_id: str, level: int, related_limit: int, related_offset: int) -> dict:
        if record_id not in self.by_id:
            return {'found': False, 'record': None}
        group, record = self.by_id[record_id]
        result = {'found': True, 'kind': group, 'record': copy.deepcopy(record)}
        if level == 0:
            return result
        ids, provenance = self.relevant(record_id)
        ids[group].discard(record_id)
        related = {}
        for kind, values in ids.items():
            if kind == 'sources' and level < 2:
                continue
            items = [copy.deepcopy(self.records[kind][item_id]) for item_id in sorted(values)]
            if kind == 'evidence' and level < 2:
                for item in items:
                    item.pop('premise_claim_ids')
            related[kind] = page(items, related_limit, related_offset)
        gaps = []
        for path, item in sorted(provenance.items()):
            values = item.get('follow_up_gaps', []) + item.get('deferred', [])
            if values:
                gaps.append({'path': path, 'gaps': values})
        result.update(related=related, gaps=page(gaps, related_limit, related_offset))
        if level == 2:
            result['provenance'] = page([{'path': path, 'record': item} for path, item in sorted(provenance.items())],
                                         related_limit, related_offset)
        return result

    def lookup(self, record_id: str, *, level=0, related_limit=50, related_offset=0) -> dict:
        bound(level, 0, 2, 'level')
        bound(related_limit, 1, 1000, 'related_limit')
        bound(related_offset, 0, sys.maxsize, 'related_offset')
        return self.envelope('lookup', **self.view(record_id, level, related_limit, related_offset))

    def search(self, text='', *, claim_class=None, uncertainty=None, state=None,
               limit=20, offset=0, level=0, related_limit=50) -> dict:
        bound(limit, 1, 100, 'limit')
        bound(offset, 0, sys.maxsize, 'offset')
        bound(level, 0, 2, 'level')
        bound(related_limit, 1, 1000, 'related_limit')
        query = set(tokens(text))
        hits = []
        for cid, document in self.documents.items():
            claim = self.records['claims'][cid]
            if any(value is not None and claim[field] != value for field, value in
                   (('class', claim_class), ('uncertainty', uncertainty), ('state', state))):
                continue
            counts = sum(document.values(), Counter())
            if not query <= counts.keys():
                continue
            score = sum(counts[word] for word in query)
            matched = sorted(record_id for record_id, terms in document.items() if query.intersection(terms))
            hits.append((score, cid, matched))
        hits.sort(key=lambda hit: (-hit[0], hit[1]))
        results = page(hits, limit, offset)
        results['items'] = [dict(self.view(cid, level, related_limit, 0), relevance=score,
                                 matched_record_ids=matched) for score, cid, matched in results['items']]
        return self.envelope('search', query=text, filters={'class': claim_class, 'uncertainty': uncertainty,
                             'state': state}, ranking='keyword_relevance_only', **results)

    def walk(self, seed: str, *, reverse: bool, direction='both', connector_type=None,
             include_retired=False, depth=1, limit=20, level=0, related_limit=50) -> dict:
        bound(depth, 0, 10, 'depth')
        bound(limit, 1, 100, 'limit')
        bound(level, 0, 2, 'level')
        bound(related_limit, 1, 1000, 'related_limit')
        if seed not in self.records['claims']:
            raise Invalid('Traversal requires a canonical claim ID')
        if direction not in ('incoming', 'outgoing', 'both') or connector_type not in (None, 'dependency', 'coupling'):
            raise Invalid('Unsupported traversal filter')
        adjacency = {}

        def edge(start, end, relation, via, **extra):
            adjacency.setdefault(start, []).append({'from': start, 'to': end, 'relation': relation,
                                                     'via': via, **extra})

        for connector in self.records['graph'].values():
            if connector['state'] == 'retired' and not include_retired:
                continue
            if reverse and connector['type'] != 'dependency':
                continue
            if not reverse and connector_type is not None and connector['type'] != connector_type:
                continue
            a, b = connector['from'], connector['to']
            extra = {'connector_state': connector['state'], 'evidence_ids': connector['evidence_ids']}
            if reverse or direction in ('incoming', 'both'):
                edge(b, a, connector['type'], connector['id'], **extra)
            if not reverse and direction in ('outgoing', 'both'):
                edge(a, b, connector['type'], connector['id'], **extra)
        if reverse:
            for evidence in self.records['evidence'].values():
                for premise in evidence['premise_claim_ids']:
                    for consumer in evidence['claim_ids']:
                        edge(premise, consumer, 'evidence_premise', evidence['id'],
                             premise_claim_ids=evidence['premise_claim_ids'])
        for edges in adjacency.values():
            edges.sort(key=lambda item: (item['relation'], item['via'], item['to']))
        seen, queue, hits = {seed}, deque([(seed, [])]), []
        truncated = False
        while queue:
            node, path = queue.popleft()
            if len(path) >= depth:
                continue
            for step in adjacency.get(node, []):
                if step['to'] in seen:
                    continue
                if len(hits) == limit:
                    truncated = True
                    queue.clear()
                    break
                target = step['to']
                seen.add(target)
                extended = path + [step]
                hits.append({'claim': self.view(target, level, related_limit, 0), 'path': copy.deepcopy(extended)})
                queue.append((target, extended))
        return self.envelope('dependents' if reverse else 'traverse', seed=seed, depth=depth,
                             filters={'direction': 'reverse_dependency' if reverse else direction,
                                      'connector_type': 'dependency_and_premises' if reverse else connector_type,
                                      'include_retired_connectors': include_retired},
                             items=hits, truncated=truncated)

    def traverse(self, seed: str, **options) -> dict:
        return self.walk(seed, reverse=False, **options)

    def dependents(self, seed: str, **options) -> dict:
        return self.walk(seed, reverse=True, **options)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--manifest-sha256', help='Require this exact build manifest digest')
    sub = parser.add_subparsers(dest='command', required=True)
    lookup = sub.add_parser('lookup')
    lookup.add_argument('record_id')
    lookup.add_argument('--related-offset', type=int, default=0)
    search = sub.add_parser('search')
    search.add_argument('text', nargs='?', default='')
    search.add_argument('--class', dest='claim_class')
    search.add_argument('--uncertainty', choices=('low', 'medium', 'high'))
    search.add_argument('--state', choices=('active', 'retired'))
    search.add_argument('--offset', type=int, default=0)
    for name in ('traverse', 'dependents'):
        walk = sub.add_parser(name)
        walk.add_argument('seed')
        walk.add_argument('--depth', type=int, default=1)
        walk.add_argument('--include-retired', action='store_true')
        if name == 'traverse':
            walk.add_argument('--direction', choices=('incoming', 'outgoing', 'both'), default='both')
            walk.add_argument('--connector-type', choices=('dependency', 'coupling'))
    for command in (lookup, search, *[sub.choices[name] for name in ('traverse', 'dependents')]):
        command.add_argument('--level', type=int, choices=(0, 1, 2), default=0)
        command.add_argument('--related-limit', type=int, default=50)
        if command != lookup:
            command.add_argument('--limit', type=int, default=20)
    args = vars(parser.parse_args())
    command = args.pop('command')
    try:
        knowledge = Knowledge(args.pop('package'), args.pop('manifest_sha256'))
        result = getattr(knowledge, command)(**args)
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    sys.stdout.buffer.write(json_bytes(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
