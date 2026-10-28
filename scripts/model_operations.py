"""Recorded model judgments supplied by external agents; no agent execution."""
from __future__ import annotations

import copy
import re

from scripts.model import CANONICAL_ROOTS, digest, fail, family, indexes, no_duplicates
from scripts.temporal import temporal_scope

OUTCOMES = {'equivalent', 'overlap', 'distinct', 'unresolved'}
UNCERTAINTY = {'low', 'medium', 'high'}
LOCAL_ID = re.compile(r'[a-z][a-z0-9_-]{0,63}')


def model_digest(state):
    return digest({'records': {p: r for p, r in state.items() if family(p) in CANONICAL_ROOTS},
                   'operations': operation_records(state)})


def operation_records(state):
    result = {}
    for path, record in sorted(state.items()):
        if family(path) not in ('closure', 'maintenance'):
            continue
        if family(path) == 'maintenance' and record['status'] != 'completed':
            continue
        for op in record.get('model_operations', []):
            fail(isinstance(op, dict) and isinstance(op.get('id'), str) and
                 LOCAL_ID.fullmatch(op['id']) is not None, 'Invalid model operation ID')
            ref = record['id'] + '#' + op['id']
            fail(ref not in result, 'Duplicate model operation: ' + ref)
            result[ref] = op
    return result


def validate_operations(state, policy_root=None):
    idx = indexes(state)
    records = {r['id']: (kind, r) for kind in CANONICAL_ROOTS for r in idx.get(kind, {}).values()}
    known = set(records) | set(idx.get('submission',{})) | set(idx.get('closure',{})) | set(idx.get('maintenance',{}))
    ops = operation_records(state)
    replaced, successors, comparison_roots, fingerprints = {}, {}, set(), set()
    common = {'id', 'kind', 'subject_ids', 'basis_ids', 'reason', 'read_sha256'}
    for ref, op in ops.items():
        fail(isinstance(op, dict) and LOCAL_ID.fullmatch(op.get('id', '')) is not None,
             'Model operations need a local lowercase ID')
        kind = op.get('kind')
        fields = {'comparison': {'outcome', 'supersedes'},
                  'reassessment': {'uncertainty', 'predecessors', 'previous_uncertainty'},
                  'linkage': {'record', 'previous_sha256'}}
        fail(isinstance(kind, str) and kind in fields and set(op) == common | fields[kind], 'Unexpected model operation fields')
        subjects, basis = op['subject_ids'], op['basis_ids']
        fail(isinstance(subjects, list) and 1 <= len(subjects) <= 200 and
             all(isinstance(v, str) and v in records for v in subjects), 'Unknown model operation subject')
        no_duplicates(subjects, 'operation subjects')
        fail(isinstance(basis, list) and 1 <= len(basis) <= 200 and
             all(isinstance(v, str) and v in known for v in basis), 'Unknown model operation basis')
        no_duplicates(basis, 'operation basis')
        fail(isinstance(op['reason'], str) and bool(op['reason'].strip()), 'Operation needs a reason')
        reads = op['read_sha256']
        fail(isinstance(reads, dict) and set(subjects + basis) <= set(reads) and
             all(key in known | set(ops) and isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value)
                 for key,value in reads.items()), 'Operation needs digests of its subjects and supplied basis')
        fail(ref.split('#')[0] not in reads and ref not in reads, 'An operation cannot cite its own receipt as its basis')
        fingerprint = digest({k:v for k,v in op.items() if k not in ('id','reason')})
        fail(fingerprint not in fingerprints, 'Duplicate model operation result')
        fingerprints.add(fingerprint)
        if kind == 'comparison':
            fail(len(subjects) == 2 and len({records[s][0] for s in subjects}) == 1,
                 'Comparison needs two records of the same kind')
            fail(records[subjects[0]][0] in ('claims','sources','evidence','questions'), 'Unsupported comparison kind')
            fail(isinstance(op['outcome'], str) and op['outcome'] in OUTCOMES, 'Invalid comparison outcome')
            previous = op['supersedes']
            fail(previous is None or (isinstance(previous, str) and previous in ops),
                 'Unknown comparison predecessor')
            if previous is not None:
                fail(previous in reads, 'Comparison predecessor needs a read digest')
                older = ops[previous]
                fail(older.get('kind') == kind and isinstance(older.get('subject_ids'),list) and
                     sorted(older['subject_ids']) == sorted(subjects),
                     'Comparison predecessor has different subjects')
                fail(previous not in replaced, 'Comparison history branches')
                replaced[previous] = ref
            else:
                pair = tuple(sorted(subjects))
                fail(pair not in comparison_roots, 'Comparison pair already has a decision; supersede its current result')
                comparison_roots.add(pair)
        elif kind == 'reassessment':
            fail(all(records[s][0] == 'claims' for s in subjects), 'Reassessment subjects must be claims')
            fail(isinstance(op['uncertainty'], str) and op['uncertainty'] in UNCERTAINTY, 'Invalid reassessment uncertainty')
            fail(isinstance(op['predecessors'], dict) and set(op['predecessors']) == set(subjects),
                 'Reassessment needs a predecessor for each claim')
            fail(isinstance(op['previous_uncertainty'], dict) and
                 set(op['previous_uncertainty']) == set(subjects) and
                 all(isinstance(v,str) and v in UNCERTAINTY for v in op['previous_uncertainty'].values()),
                 'Reassessment needs previous uncertainty for each claim')
            for subject in subjects:
                previous = op['predecessors'][subject]
                fail(previous is None or (isinstance(previous, str) and previous in ops),
                     'Unknown reassessment predecessor')
                if previous is not None:
                    fail(previous in reads, 'Reassessment predecessor needs a read digest')
                    older = ops[previous]
                    fail(older.get('kind') == kind and subject in older.get('subject_ids',[]),
                         'Reassessment predecessor has a different subject')
                    fail(older['uncertainty'] == op['previous_uncertainty'][subject],
                         'Reassessment does not continue previous uncertainty')
                key = (subject, previous)
                fail(key not in successors, 'Reassessment history branches')
                successors[key] = ref
        else:
            record = op['record']
            fail(isinstance(record, dict) and isinstance(record.get('id'),str) and record['id'] in idx.get('graph', {}),
                 'Linkage needs a canonical relationship')
            if policy_root is not None:
                from jsonschema import Draft202012Validator
                from scripts.model import read_data
                schema = read_data(policy_root / 'docs/schemas/graph.schema.json')
                fail(not list(Draft202012Validator(schema).iter_errors(record)), 'Invalid historical relationship record')
            fail(set(record['evidence_ids']) <= set(idx.get('evidence', {})), 'Unknown linkage evidence')
            fail(set(record['evidence_ids']) <= set(reads), 'Linkage evidence needs read digests')
            fail(set(subjects) == {record.get('from'), record.get('to')}, 'Linkage subjects differ from endpoints')
            fail(op['previous_sha256'] is None or
                 isinstance(op['previous_sha256'], str) and re.fullmatch('[0-9a-f]{64}', op['previous_sha256']),
                 'Invalid relationship predecessor digest')
    # Explicit predecessor chains, never caller timestamps, establish current results.
    from scripts.model import acyclic
    acyclic(list(replaced.items()), 'comparison history')
    acyclic([(ref, previous) for ref, op in ops.items() if op['kind'] == 'reassessment'
             for previous in op['predecessors'].values() if previous is not None], 'assessment history')
    groups = equivalence_groups(state, ops=ops)
    for ref, op in ops.items():
        if op['kind'] == 'comparison' and ref not in replaced and op['outcome'] == 'equivalent':
            a, b = [records[s][1] for s in op['subject_ids']]
            kind = records[op['subject_ids'][0]][0]
            if kind == 'sources':
                same = lambda key: ' '.join(str(a.get(key) or '').split()) == ' '.join(str(b.get(key) or '').split())
                fail(all(same(key) for key in ('kind','date','locator','excerpt')),
                     'Source equivalence must preserve the supplied version and anchored passage')
                for key in ('version','content_sha256'):
                    av,bv = [r.get('ancestry',{}).get(key) for r in (a,b)]
                    fail(not av or not bv or av == bv, 'Distinct supplied source versions cannot be grouped')
            elif kind == 'claims':
                fail(a['class'] == b['class'] and temporal_scope(a.get('valid_time')) ==
                     temporal_scope(b.get('valid_time')), 'Equivalent claims need the same class and temporal scope')
            elif kind == 'evidence':
                roots = lambda values: {groups[v][0] for v in values}
                fail(a['kind'] == b['kind'] and a['independent'] == b['independent'] and
                     roots(a['source_ids']) == roots(b['source_ids']) and
                     roots(a['premise_claim_ids']) == roots(b['premise_claim_ids']),
                     'Evidence equivalence must preserve origins, independence and joint premises')
        if op['kind'] == 'comparison' and ref not in replaced and op['outcome'] != 'equivalent':
            a, b = op['subject_ids']
            fail(groups[a] != groups[b], 'Non-equivalent records cannot belong to the same equivalence group')
    root = lambda value: groups[value][0]
    graph = idx.get('graph',{})
    for edge in graph.values():
        fail(root(edge['from']) != root(edge['to']), 'Equivalence creates a self-connector')
    acyclic([(root(r['from']), root(r['to'])) for r in graph.values()
             if r['type']=='dependency' and r['state']=='active'], 'grouped dependency')
    premise_edges = [(root(cid),root(premise)) for item in idx.get('evidence',{}).values()
                     for cid in item['claim_ids'] for premise in item['premise_claim_ids']]
    acyclic(premise_edges, 'grouped evidential self-validation')
    current = current_assessments(ops)
    for subject, ref in current.items():
        fail(records[subject][1]['uncertainty'] == ops[ref]['uncertainty'],
             'Current claim uncertainty differs from its assessment history')
    return ops


def equivalence_groups(state, *, ops=None):
    ids = [r['id'] for p, r in state.items() if family(p) in CANONICAL_ROOTS]
    parent = {v: v for v in ids}
    def root(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v
    ops = operation_records(state) if ops is None else ops
    replaced = {op['supersedes'] for op in ops.values() if op['kind'] == 'comparison' and op['supersedes']}
    for ref, op in ops.items():
        if op['kind'] == 'comparison' and ref not in replaced and op['outcome'] == 'equivalent':
            a, b = [root(v) for v in op['subject_ids']]
            parent[max(a, b)] = min(a, b)
    members = {}
    for value in sorted(ids):
        members.setdefault(root(value), []).append(value)
    return {value: members[root(value)] for value in ids}


def current_assessments(ops):
    current = {}
    superseded = {(subject, previous) for op in ops.values() if op['kind'] == 'reassessment'
                  for subject, previous in op['predecessors'].items() if previous is not None}
    for ref, op in ops.items():
        if op['kind'] == 'reassessment':
            for subject in op['subject_ids']:
                if (subject, ref) not in superseded:
                    fail(subject not in current, 'Multiple current assessments for a claim')
                    current[subject] = ref
    return current


def apply_operations(state, operations, *, read_state=None):
    """Apply supplied judgments to an in-memory proposal, preserving all original IDs."""
    fail(isinstance(operations, list) and len(operations) <= 200, 'At most 200 model operations per record')
    result, changes, written = [], {}, set()
    idx = indexes(state)
    by_id = {r['id']: (p, r) for p, r in state.items() if family(p) in CANONICAL_ROOTS}
    current = current_assessments(operation_records(state))
    reads = {r['id']:r for r in state.values()}
    reads.update(operation_records(state))
    if read_state is not None:
        reads.update({r['id']:r for r in read_state.values()})
        reads.update(operation_records(read_state))
    for supplied in operations:
        op = copy.deepcopy(supplied)
        fail(isinstance(op, dict) and isinstance(op.get('kind'), str) and op['kind'] in ('comparison', 'linkage', 'reassessment'),
             'Unknown model operation kind')
        fail('read_sha256' not in op, 'Read digests are supplied by the trusted writer')
        fail(isinstance(op.get('subject_ids'),list) and isinstance(op.get('basis_ids'),list) and
             isinstance(op.get('predecessors',{}),dict), 'Operation subjects, basis and predecessors have invalid shapes')
        refs=op.get('subject_ids',[])+op.get('basis_ids',[])
        if op.get('supersedes') is not None:
            refs.append(op['supersedes'])
        refs.extend(v for v in op.get('predecessors',{}).values() if v is not None)
        if op['kind']=='linkage' and isinstance(op.get('record'),dict):
            refs.extend(op['record'].get('evidence_ids',[]))
            if op['record'].get('id') in reads:
                refs.append(op['record']['id'])
        fail(all(isinstance(v,str) and v in reads for v in refs), 'Unknown model operation read')
        op['read_sha256']={v:digest(reads[v]) for v in sorted(set(refs))}
        if op['kind'] == 'reassessment':
            fail('previous_uncertainty' not in op, 'Previous uncertainty is supplied by the trusted writer')
            subjects = op.get('subject_ids', [])
            fail(subjects and all(isinstance(v,str) and v in idx.get('claims', {}) for v in subjects), 'Unknown reassessment claim')
            fail(op.get('predecessors') == {s: current.get(s) for s in subjects}, 'Stale reassessment predecessor')
            op['previous_uncertainty'] = {s: by_id[s][1]['uncertainty'] for s in subjects}
            for subject in subjects:
                fail(subject not in written, 'Only one write per record in a model-operation batch')
                written.add(subject)
                path, record = by_id[subject]
                record = copy.deepcopy(record)
                record['uncertainty'] = op.get('uncertainty')
                state[path] = changes[path] = record
        elif op['kind'] == 'linkage':
            record = op.get('record', {})
            fail(isinstance(record, dict), 'Linkage record must be an object')
            rid = record.get('id')
            fail(isinstance(rid, str) and re.fullmatch('R-[0-9a-f]{32}', rid), 'Invalid relationship ID')
            fail(rid not in written, 'Only one write per record in a model-operation batch')
            written.add(rid)
            previous = idx.get('graph', {}).get(rid)
            fail(op.get('previous_sha256') == (digest(previous) if previous else None), 'Stale relationship write')
            path = 'graph/' + rid + '.yaml'
            state[path] = changes[path] = copy.deepcopy(record)
        result.append(op)
    return result, changes
