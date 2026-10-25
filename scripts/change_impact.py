#!/usr/bin/env python3
"""Compare pinned knowledge revisions and explain potential reassessment paths."""
from __future__ import annotations

import argparse
from collections import defaultdict
import heapq
from itertools import count
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.build_knowledge import compile_revision, json_bytes, sha256
from scripts.model import CANONICAL_ROOTS, Invalid


def changes(before: dict, after: dict) -> list[dict]:
    result = []
    missing = object()
    for group in sorted(CANONICAL_ROOTS):
        for record_id in sorted(before[group].keys() | after[group].keys()):
            old, new = before[group].get(record_id), after[group].get(record_id)
            if old == new:
                continue
            operation = 'added' if old is None else 'removed' if new is None else 'edited'
            if old and new and old.get('state') != 'retired' and new.get('state') == 'retired':
                operation = 'retired'
            fields = sorted(key for key in (old or {}).keys() | (new or {}).keys()
                            if (old or {}).get(key, missing) != (new or {}).get(key, missing))
            support_changed = (group in ('sources', 'evidence') or
                               (group == 'claims' and 'evidence_ids' in fields) or
                               (group == 'graph' and 'evidence_ids' in fields))
            result.append({'group': group, 'id': record_id, 'operation': operation,
                           'changed_fields': fields, 'support_changed': support_changed,
                           'before': old, 'after': new})
    return result


def impact_graph(records: dict) -> tuple[dict, dict]:
    """Reverse only declared support/dependencies; keep coupling in another graph."""
    hard, contextual = defaultdict(list), defaultdict(list)

    def edge(graph: dict, start: str, end: str, relation: str, via: str, **extra):
        graph[start].append({'from': start, 'to': end, 'relation': relation,
                             'via': via, **extra})

    for eid, evidence in records['evidence'].items():
        for sid in evidence['source_ids']:
            edge(hard, sid, eid, 'source_evidence', eid)
        for premise in evidence['premise_claim_ids']:
            edge(hard, premise, eid, 'evidence_premise', eid,
                 premise_claim_ids=evidence['premise_claim_ids'])
    for cid, claim in records['claims'].items():
        for eid in claim['evidence_ids']:
            edge(hard, eid, cid, 'evidence_claim', eid)
    for rid, connector in records['graph'].items():
        if connector['state'] != 'active':
            continue
        for eid in connector['evidence_ids']:
            edge(hard, eid, rid, 'connector_evidence', rid)
        if connector['type'] == 'dependency':
            edge(hard, connector['to'], connector['from'], 'dependency', rid)
            edge(hard, rid, connector['from'], 'dependency_connector', rid)
        else:
            edge(contextual, connector['from'], connector['to'], 'coupling', rid)
            edge(contextual, connector['to'], connector['from'], 'coupling', rid)
            for cid in (connector['from'], connector['to']):
                edge(contextual, rid, cid, 'coupling_connector', rid)
    for graph in (hard, contextual):
        for edges in graph.values():
            edges.sort(key=lambda step: (step['relation'], step['via'], step['to']))
    return hard, contextual


def path_key(path: list[dict]) -> tuple:
    return tuple((step['relation'], step['via'], step['to']) for step in path)


def explanation_paths(seed: str, records: dict, hard: dict, contextual: dict) -> tuple[dict, dict]:
    """One deterministic shortest explanation per claim and impact type.

    Prefer fewer claim consumers, then fewer steps, then lexical edge order.
    A contextual step terminates traversal; it never becomes hard propagation.
    """
    sequence = count()
    queue = [(0, 0, (), next(sequence), seed, [])]
    visited = {}
    while queue:
        hops, _, _, _, node, path = heapq.heappop(queue)
        if node in visited:
            continue
        visited[node] = (hops, path)
        for step in hard.get(node, []):
            target = step['to']
            if target not in visited:
                extended = path + [step]
                distance = hops + (target in records['claims'])
                heapq.heappush(queue, (distance, len(extended), path_key(extended),
                                       next(sequence), target, extended))
    dependency_paths = {node: (hops, path) for node, (hops, path) in visited.items()
                        if node in records['claims'] and node != seed}
    context_paths = {}
    for node, (hops, path) in visited.items():
        for step in contextual.get(node, []):
            target = step['to']
            if target == seed:
                continue
            extended = path + [step]
            candidate = (hops + 1, len(extended), path_key(extended))
            previous = context_paths.get(target)
            if previous is None or candidate < (previous[0], len(previous[1]), path_key(previous[1])):
                context_paths[target] = (hops + 1, extended)
    return dependency_paths, context_paths


def analyze(before: dict, after: dict) -> dict:
    """Compare canonical projections already validated by compile_revision."""
    delta = changes(before, after)
    impacts = {'dependency_impacts': [], 'contextual_impacts': []}
    for snapshot_name, records in (('before', before), ('after', after)):
        hard, contextual = impact_graph(records)
        for change in delta:
            seed = change['id']
            if seed not in records[change['group']]:
                continue
            paths = explanation_paths(seed, records, hard, contextual)
            for group, explanations in zip(impacts, paths):
                for cid, (hops, path) in sorted(explanations.items()):
                    old_claim, new_claim = before['claims'].get(cid), after['claims'].get(cid)
                    impacts[group].append({
                        'claim_id': cid, 'change_id': seed, 'change_group': change['group'],
                        'snapshot': snapshot_name, 'assessment': 'potentially_affected',
                        'proximity': 'direct' if hops == 1 else 'transitive',
                        'claim_hops': hops, 'path': path,
                        'before_state': old_claim['state'] if old_claim else None,
                        'after_state': new_claim['state'] if new_claim else None,
                    })
    return {'format_version': '1.0', 'changes': delta, **impacts,
            'semantic_verdict': 'not assessed; potential impact does not establish invalidation'}


def compare_revisions(repo: Path, before: str, after: str) -> dict:
    """Validate both pinned revisions and return a deterministic, read-only report."""
    packages = [compile_revision(repo, revision) for revision in (before, after)]
    projections = [json.loads(package['knowledge.json']) for package in packages]
    report = analyze(*(projection['records'] for projection in projections))
    for name, package in zip(('before', 'after'), packages):
        manifest = json.loads(package['manifest.json'])
        report[name] = {'source_revision': manifest['source_revision'],
                        'input_tree_sha256': manifest['input_tree_sha256'],
                        'manifest_sha256': sha256(package['manifest.json'])}
    return report


def readable_summary(report: dict) -> str:
    lines = [f"Knowledge changes: {report['before']['source_revision']} -> {report['after']['source_revision']}",
             f"{len(report['changes'])} changed records. Potential reassessment only; no invalidation determined."]
    for change in report['changes']:
        fields = ', '.join(change['changed_fields'])
        lines.append(f"{change['operation']}: {change['group']}/{change['id']} ({fields})")
    for group, label in (('dependency_impacts', 'Dependency/support'), ('contextual_impacts', 'Contextual')):
        for impact in report[group]:
            route = impact['change_id'] + ''.join(
                f" --{step['relation']}[{step['via']}]--> {step['to']}" for step in impact['path'])
            lines.append(f"{label} {impact['proximity']} [{impact['snapshot']}]: {route}")
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--before', required=True, help='Local Git commit/ref before the change')
    parser.add_argument('--after', required=True, help='Local Git commit/ref after the change')
    parser.add_argument('--format', choices=('json', 'text'), default='json')
    args = parser.parse_args()
    try:
        report = compare_revisions(args.repo, args.before, args.after)
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    if args.format == 'json':
        sys.stdout.buffer.write(json_bytes(report))
    else:
        print(readable_summary(report), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
