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
from scripts.temporal import applicability, point
from scripts.model_operations import current_assessments, equivalence_groups, model_digest, operation_records


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
        self.state = state
        self.model_sha256 = model_digest(state)
        self.operations = operation_records(state)
        self.groups = equivalence_groups(state, ops=self.operations)
        self.current_assessments = current_assessments(self.operations)
        self.supplied_assessments = {cid:[] for cid in self.records['claims']}
        provenance=self.knowledge['provenance']
        runs={r['id']:r for r in provenance.values() if r.get('id','').startswith('RUN-')}
        for receipt in provenance.values():
            if receipt.get('id','').startswith('BC-'):
                run=runs[receipt['submission_id']]
                candidates={r['id']:r for r in run['claims']}
                for disposition in receipt['claim_dispositions']:
                    cid=disposition['claim_id']
                    if cid is not None:
                        candidate=candidates[disposition['candidate_id']]
                        self.supplied_assessments[cid].append({'id':run['id']+'#'+candidate['id'],
                            'kind':'supplied_assessment','uncertainty':candidate['uncertainty'],
                            'disposition':disposition['disposition']})
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
                for sid in self.source_ancestors(evidence['source_ids']):
                    source = self.records['sources'][sid]
                    texts[sid] = ' '.join(source[key] or '' for key in ('title', 'uri', 'date', 'locator', 'excerpt'))
            self.documents[cid] = {record_id: Counter(tokens(text)) for record_id, text in texts.items()}

    def source_ancestors(self, source_ids) -> set[str]:
        result, pending = set(source_ids), list(source_ids)
        while pending:
            source = self.records['sources'][pending.pop()]
            for parent in source.get('ancestry', {}).get('parent_source_ids', []):
                if parent not in result:
                    result.add(parent)
                    pending.append(parent)
        return result

    def envelope(self, operation: str, **result) -> dict:
        return {'format_version': '1.1', 'build': dict(self.build), 'model_sha256':self.model_sha256,
                'operation': operation, **result}

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
        ids['sources'] = self.source_ancestors(ids['sources'])
        for cid in ids['claims']:
            ids['questions'].update(self.knowledge['reverse_links']['claims'][cid]['question_ids'])
        paths = {f'{kind}/{item_id}.yaml' for kind, values in ids.items() for item_id in values}
        provenance = self.knowledge['provenance']
        selected, runs = {}, set()
        relevant_ids=set().union(*ids.values())
        for path, item in provenance.items():
            kind = family(path)
            if ((kind == 'closure' and paths.intersection(item['touched_files'])) or
                    (kind == 'maintenance' and (paths.intersection(item['touched_files']) or
                                               ids['claims'].intersection(item['claim_ids']))) or
                    any(relevant_ids.intersection(op['subject_ids']) for op in item.get('model_operations',[]))):
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
        members = self.groups[record_id]
        result['equivalence_group'] = {'id':members[0], 'members':page(members,related_limit,related_offset)}
        if 'state' in record:
            states={self.by_id[cid][1]['state'] for cid in members}
            result['equivalence_group']['states']=sorted(states)
        if group == 'claims':
            ratings = [{'claim_id':cid, 'uncertainty':self.records['claims'][cid]['uncertainty'],
                        'assessment':self.current_assessments.get(cid)} for cid in members]
            for cid in members:
                if cid not in self.current_assessments:
                    ratings.extend({'claim_id':cid,'uncertainty':item['uncertainty'],'assessment':item['id']}
                        for item in self.supplied_assessments[cid]
                        if item['uncertainty'] != self.records['claims'][cid]['uncertainty'])
            values = {item['uncertainty'] for item in ratings}
            result['current_assessment'] = {'status':'agreed' if len(values)==1 else 'disputed',
                    'uncertainty':next(iter(values)) if len(values)==1 else None,
                    'members':page(ratings,related_limit,related_offset)}
        if level == 0:
            return result
        ids, provenance = self.relevant(record_id)
        for member in members:
            if member != record_id:
                more_ids, more_provenance=self.relevant(member)
                for kind,values in more_ids.items():
                    ids[kind].update(values)
                provenance.update(more_provenance)
        ids[group].difference_update(members)
        related = {}
        for kind, values in ids.items():
            if kind == 'sources' and level < 2:
                continue
            items, seen = [], set()
            for item_id in sorted(values):
                identity=self.groups[item_id][0]
                if identity in seen:
                    continue
                seen.add(identity)
                view=self.view(item_id,0,related_limit,related_offset)
                item=view['record']
                item['equivalence_group']=view['equivalence_group']
                if 'current_assessment' in view:
                    item['current_assessment']=view['current_assessment']
                items.append(item)
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
               limit=20, offset=0, level=0, related_limit=50, kind='claims') -> dict:
        if kind != 'claims':
            if any(v is not None for v in (claim_class,uncertainty,state)):
                raise Invalid('Claim filters require the claims record kind')
            return self.candidates(text,kind=kind,limit=limit,offset=offset,grouped=True)
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
        seen, grouped = set(), []
        for hit in hits:
            identity = self.groups[hit[1]][0]
            if identity not in seen:
                seen.add(identity)
                grouped.append(hit)
        hits = grouped
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
            if reverse:
                for eid in connector['evidence_ids']:
                    evidence = self.records['evidence'][eid]
                    for premise in evidence['premise_claim_ids']:
                        edge(premise, a, 'connector_evidence_premise', eid,
                             connector_id=connector['id'], connector_state=connector['state'],
                             premise_claim_ids=evidence['premise_claim_ids'])
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

    def valid_at(self, at: str, *, limit=20, offset=0, level=0, related_limit=50) -> dict:
        bound(limit, 1, 100, 'limit')
        bound(offset, 0, sys.maxsize, 'offset')
        bound(level, 0, 2, 'level')
        bound(related_limit, 1, 1000, 'related_limit')
        try:
            query = point(at)
        except ValueError as exc:
            raise Invalid(str(exc)) from exc
        groups = {'matches': [], 'unresolved': []}
        outside = 0
        for cid, claim in sorted(self.records['claims'].items()):
            status, reason = applicability(claim.get('valid_time'), query)
            if status == 'outside':
                outside += 1
            else:
                groups[status].append((cid, reason))
        result = {}
        for status, items in groups.items():
            seen,unique=set(),[]
            for item in items:
                identity=self.groups[item[0]][0]
                if identity not in seen:
                    seen.add(identity);unique.append(item)
            items=unique
            collection = page(items, limit, offset)
            collection['items'] = [dict(self.view(cid, level, related_limit, 0), temporal_status=status,
                                        temporal_reason=reason) for cid, reason in collection['items']]
            result[status] = collection
        return self.envelope('valid_at', at=at, interpretation='recorded_applicability_only',
                             outside_recorded_intervals=outside, **result)

    def lineage(self, evidence_id: str | None = None, *, limit=20, offset=0, max_bytes=32768) -> dict:
        from scripts.source_lineage import source_lineage
        report = source_lineage(self, evidence_id, include_peer_lists=limit is None)
        if limit is None:
            return report  # Retain the native programmatic report for existing callers.
        from scripts.model_context import bounded_page, card
        items=[]
        for kind in ('sources','evidence','claims','connectors'):
            for node in report[kind].values():
                record=node.get('record',node)
                items.append(card('graph' if kind=='connectors' else kind,record))
        for flag in report['flags']:
            items.append({'id':flag['id'],'kind':'lineage_flag','flag_kind':flag['kind'],
                          'basis':flag['basis'],'evidence_count':len(flag['evidence_ids']),
                          'source_count':len(flag['source_ids'])})
        return bounded_page(self,'lineage',items,focus_evidence_id=evidence_id,
                            interpretation=report['interpretation'],limit=limit,offset=offset,max_bytes=max_bytes)

    def candidates(self, text='', **options):
        from scripts.model_context import candidates
        return candidates(self,text,**options)

    def context(self, record_id, **options):
        from scripts.model_context import context
        return context(self,record_id,**options)

    def passage(self, record_id, **options):
        from scripts.model_context import passage
        return passage(self,record_id,**options)

    def assessments(self, record_id, **options):
        from scripts.model_context import assessment_history
        return assessment_history(self,record_id,**options)

    def changes(self, before_package, **options):
        from scripts.model_context import changes
        return changes(self,before_package,**options)

    def lineage_flag(self, flag_id, *, limit=20, offset=0, max_bytes=32768):
        from scripts.source_lineage import source_lineage
        from scripts.model_context import bounded_page, card
        report=source_lineage(self,include_peer_lists=False)
        flag=next((f for f in report['flags'] if f['id']==flag_id),None)
        if flag is None:
            raise Invalid('Unknown lineage flag')
        ids=sorted(set(flag['source_ids']+flag['evidence_ids']+flag['associated_claim_ids']))
        return bounded_page(self,'lineage_flag',[card(*self.by_id[v]) for v in ids],
                            flag_id=flag_id,flag_kind=flag['kind'],basis=flag['basis'],
                            independence_assessment=flag['independence_assessment'],
                            limit=limit,offset=offset,max_bytes=max_bytes)


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
    search.add_argument('--kind',choices=CANONICAL_ROOTS,default='claims')
    temporal = sub.add_parser('valid-at')
    temporal.add_argument('at')
    temporal.add_argument('--offset', type=int, default=0)
    lineage = sub.add_parser('lineage')
    lineage.add_argument('--evidence', dest='evidence_id')
    candidate = sub.add_parser('candidates')
    candidate.add_argument('text',nargs='?',default='')
    candidate.add_argument('--kind',choices=CANONICAL_ROOTS,default='claims')
    context = sub.add_parser('context')
    context.add_argument('record_id')
    context.add_argument('--purpose',choices=('comparison','linkage','reassessment'),default='comparison')
    assessment = sub.add_parser('assessments')
    assessment.add_argument('record_id')
    change=sub.add_parser('changes')
    change.add_argument('--before-package',required=True,type=Path)
    flag=sub.add_parser('lineage-flag')
    flag.add_argument('flag_id')
    passage = sub.add_parser('passage')
    passage.add_argument('record_id')
    passage.add_argument('--field')
    passage.add_argument('--offset',type=int,default=0)
    passage.add_argument('--max-bytes',type=int,default=32768)
    for command in (candidate,context,assessment,lineage,change,flag):
        command.add_argument('--limit',type=int,default=20)
        command.add_argument('--offset',type=int,default=0)
        command.add_argument('--max-bytes',type=int,default=32768)
    for name in ('traverse', 'dependents'):
        walk = sub.add_parser(name)
        walk.add_argument('seed')
        walk.add_argument('--depth', type=int, default=1)
        walk.add_argument('--include-retired', action='store_true')
        if name == 'traverse':
            walk.add_argument('--direction', choices=('incoming', 'outgoing', 'both'), default='both')
            walk.add_argument('--connector-type', choices=('dependency', 'coupling'))
    for command in (lookup, search, temporal, *[sub.choices[name] for name in ('traverse', 'dependents')]):
        command.add_argument('--level', type=int, choices=(0, 1, 2), default=0)
        command.add_argument('--related-limit', type=int, default=50)
        if command != lookup:
            command.add_argument('--limit', type=int, default=20)
    args = vars(parser.parse_args())
    command = args.pop('command').replace('-', '_')
    try:
        knowledge = Knowledge(args.pop('package'), args.pop('manifest_sha256'))
        result = getattr(knowledge, command)(**args)
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    sys.stdout.buffer.write(json_bytes(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
