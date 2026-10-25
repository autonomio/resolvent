"""Derived source/evidence ancestry and review cues, never independence verdicts."""
from __future__ import annotations

from collections import defaultdict
import copy
import re
from urllib.parse import urlsplit, urlunsplit

from scripts.build_knowledge import json_bytes, sha256
from scripts.model import Invalid


def source_lineage(knowledge, evidence_id: str | None = None) -> dict:
    records = knowledge.records
    sources, evidence, claims = [records[group] for group in ('sources', 'evidence', 'claims')]
    if evidence_id is not None and evidence_id not in evidence:
        raise Invalid('Lineage focus must be a canonical evidence ID')
    source_nodes = {}
    for sid, source in sorted(sources.items()):
        ancestors = knowledge.source_ancestors([sid])
        unresolved = {}
        for ancestor in sorted(ancestors):
            item = sources[ancestor]
            reasons = []
            if item.get('ancestry', {}).get('status', 'unknown') == 'unknown':
                reasons.append('ancestry_unknown')
            if item['access'] == 'not_retrieved':
                reasons.append('not_retrieved')
            if reasons:
                unresolved[ancestor] = reasons
        source_nodes[sid] = {
            'record': copy.deepcopy(source),
            'ancestor_source_ids': sorted(ancestors - {sid}),
            'declared_original_source_ids': sorted(item for item in ancestors
                if sources[item].get('ancestry', {}).get('status') == 'original'),
            'unresolved_sources': unresolved,
            'independence_assessment': 'not_determined',
        }
    evidence_nodes = {}
    for eid, item in sorted(evidence.items()):
        upstream, pending = {eid}, [eid]
        while pending:
            current = evidence[pending.pop()]
            for cid in current['premise_claim_ids']:
                for parent in claims[cid]['evidence_ids']:
                    if parent not in upstream:
                        upstream.add(parent)
                        pending.append(parent)
        origins = set()
        for upstream_id in upstream:
            for sid in evidence[upstream_id]['source_ids']:
                origins.update(knowledge.source_ancestors([sid]))
        unresolved = {}
        for sid in sorted(origins):
            unresolved.update(source_nodes[sid]['unresolved_sources'])
        connector_ids = sorted(rid for rid, connector in records['graph'].items()
                                if eid in connector['evidence_ids'])
        evidence_nodes[eid] = {
            'record': copy.deepcopy(item), 'upstream_evidence_ids': sorted(upstream - {eid}),
            'source_ancestry_ids': sorted(origins), 'unresolved_sources': unresolved,
            'connector_ids': connector_ids,
            'flag_ids': [], 'related_evidence_ids': [], 'independence_assessment': 'not_determined',
        }
    flags = []

    def flag(kind: str, basis: str, key: str, source_ids: set[str], *, require_peer=True):
        members = sorted(eid for eid, node in evidence_nodes.items()
                         if source_ids.intersection(node['source_ancestry_ids']))
        if not members or (require_peer and len(members) < 2):
            return
        body = {'kind': kind, 'basis': basis, 'key': key, 'source_ids': sorted(source_ids),
                'evidence_ids': members,
                'associated_claim_ids': sorted({cid for eid in members for cid in evidence[eid]['claim_ids']} |
                    {records['graph'][rid][endpoint] for eid in members
                     for rid in evidence_nodes[eid]['connector_ids'] for endpoint in ('from', 'to')}),
                'independence_assessment': 'unresolved',
                'source_access': {sid: sources[sid]['access'] for sid in sorted(source_ids)}}
        body['id'] = sha256(json_bytes(body))
        flags.append(body)

    for sid in sorted(sources):
        flag('shared_declared_source_or_ancestor', 'deterministic_metadata', sid, {sid})
    fingerprints, uris, excerpts = defaultdict(set), defaultdict(set), defaultdict(set)
    for sid, source in sources.items():
        fingerprint = source.get('ancestry', {}).get('content_sha256')
        if fingerprint:
            fingerprints[fingerprint].add(sid)
        try:
            uri = urlsplit(source['uri'] or '')
            if uri.scheme.lower() in ('https', 'http') and uri.netloc:
                key = urlunsplit((uri.scheme.lower(), uri.netloc.lower(), uri.path, uri.query, ''))
                uris[key].add(sid)
        except ValueError:
            pass  # An opaque/unparseable locator is preserved, not guessed or fetched.
        excerpt = ' '.join(source['excerpt'].casefold().split())
        if len(excerpt) >= 80 and len(re.findall(r'\w+', excerpt)) >= 12:
            excerpts[excerpt].add(sid)
    for kind, basis, groups in (
        ('shared_declared_content_sha256', 'deterministic_metadata', fingerprints),
        ('possible_duplicate_uri', 'heuristic', uris),
        ('possible_repeated_excerpt', 'heuristic', excerpts),
    ):
        for key, members in sorted(groups.items()):
            if len(members) >= 2:
                # Avoid repeating long excerpts in the cue; native source text is retained above.
                cue = sha256(key.encode('utf-8')) if kind == 'possible_repeated_excerpt' else key
                flag(kind, basis, cue, members, require_peer=False)
    flags.sort(key=lambda item: (item['kind'], item['key'], item['id']))
    selected_evidence = set(evidence)
    if evidence_id is not None:
        flags = [item for item in flags if evidence_id in item['evidence_ids']]
        selected_evidence = {evidence_id} | {eid for item in flags for eid in item['evidence_ids']}
        for eid in list(selected_evidence):
            selected_evidence.update(evidence_nodes[eid]['upstream_evidence_ids'])
    for item in flags:
        for eid in item['evidence_ids']:
            evidence_nodes[eid]['flag_ids'].append(item['id'])
            evidence_nodes[eid]['related_evidence_ids'].extend(peer for peer in item['evidence_ids'] if peer != eid)
    selected_sources = (set(sources) if evidence_id is None else
                        {sid for eid in selected_evidence for sid in evidence_nodes[eid]['source_ancestry_ids']})
    selected_connectors = {rid for eid in selected_evidence for rid in evidence_nodes[eid]['connector_ids']}
    selected_claims = {cid for eid in selected_evidence
                       for cid in evidence[eid]['claim_ids'] + evidence[eid]['premise_claim_ids']}
    selected_claims.update(records['graph'][rid][endpoint] for rid in selected_connectors for endpoint in ('from', 'to'))
    for eid in selected_evidence:
        node = evidence_nodes[eid]
        node['flag_ids'] = sorted(set(node['flag_ids']))
        node['related_evidence_ids'] = sorted(set(node['related_evidence_ids']))
    return knowledge.envelope('lineage', focus_evidence_id=evidence_id,
        sources={sid: source_nodes[sid] for sid in sorted(selected_sources)},
        evidence={eid: evidence_nodes[eid] for eid in sorted(selected_evidence)}, flags=flags,
        connectors={rid: copy.deepcopy(records['graph'][rid]) for rid in sorted(selected_connectors)},
        claims={cid: copy.deepcopy(claims[cid]) for cid in sorted(selected_claims)},
        interpretation='Review cues only; metadata equality and search similarity do not determine independence or truth')
