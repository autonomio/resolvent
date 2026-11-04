"""Read-only question exports from a pinned, closed Knowledge package.

Selection follows recorded links, not semantic relevance. Producer material stays
producer material; inspection, citation and hashes never establish paper review.
"""
from __future__ import annotations

import copy
import json
import math

from scripts.build_knowledge import json_bytes, sha256
from scripts.model import CANONICAL_ROOTS, Invalid, family, unique_pairs
from scripts.model_context import text_page

MAX_EXPANDED_BYTES = 32 * 1024 * 1024


def parse(text):
    return json.loads(text, object_pairs_hook=unique_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))


def pointer(value, path):
    """Resolve an in-document JSON pointer only; never a URI or filesystem path."""
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('Expected a submission JSON pointer')
    parts = path[1:].split('/')
    for part in parts:
        if '~' in part.replace('~0', '').replace('~1', ''):
            raise ValueError('Invalid JSON pointer escape')
    for part in parts:
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list) and part.isascii() and part.isdigit():
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise ValueError('Missing JSON pointer')
    return value


def research_artifact(run):
    """Decode the existing Canary extension, without importing a producer runtime.

    Only local references are supported. Reconstruction checksums check transport,
    not truth, admission, source independence or completion of research.
    """
    artifacts = run['result']['artifacts']
    matches = [(i, a) for i, a in enumerate(artifacts) if a['name'] == 'canary-research.json']
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous preserved research artifact')
    index, artifact = matches[0]
    encoding = run['method_metadata'].get('canary_encoding')
    if encoding is None:
        result = parse(artifact['content'])
    else:
        if (not isinstance(encoding, dict) or encoding.get('format') != 'canary.references'
                or type(encoding.get('version')) is not int or encoding['version'] != 1):
            raise ValueError('Unsupported preserved artifact encoding')
        active = set()
        remaining = MAX_EXPANDED_BYTES

        def account(size):
            nonlocal remaining
            remaining -= size
            if remaining < 0:
                raise ValueError('Preserved artifact expansion exceeds 32 MiB')

        def unpack(node):
            account(16)  # Conservative container/separator budget, also bounds node expansion.
            if isinstance(node, list):
                return [unpack(v) for v in node]
            if not isinstance(node, dict):
                account(len(json.dumps(node, ensure_ascii=False, allow_nan=False).encode('utf-8')))
                return node
            if set(node) == {'$canary_ref'}:
                path = node['$canary_ref']
                # Native fields only: encoded extensions cannot reference themselves.
                if not isinstance(path, str):
                    raise ValueError('Invalid native reference')
                parts = path.split('/')
                if len(parts) < 2 or (parts[1] == 'result' and (len(parts) < 3 or parts[2] == 'artifacts')) or (
                        parts[1] == 'method_metadata' and (len(parts) < 3 or parts[2] in ('canary_view', 'canary_encoding'))):
                    raise ValueError('Reference targets encoded content')
                value = pointer(run, path)
                account(len(json_bytes(value)))
                return copy.deepcopy(value)
            if set(node) == {'$canary_value'}:
                i = node['$canary_value']
                if type(i) is not int or not 0 <= i < len(encoding['values']) or i in active:
                    raise ValueError('Invalid or cyclic artifact value reference')
                active.add(i)
                try:
                    return unpack(encoding['values'][i])
                finally:
                    active.remove(i)
            if set(node) == {'$canary_number'}:
                number = parse(node['$canary_number'])
                if type(number) not in (int, float) or (type(number) is float and not math.isfinite(number)):
                    raise ValueError('Invalid encoded number')
                return number
            if set(node) == {'$canary_object'}:
                result = {}
                for key, value in node['$canary_object']:
                    if not isinstance(key, str) or key in result:
                        raise ValueError('Invalid encoded object')
                    account(len(json.dumps(key, ensure_ascii=False).encode('utf-8')) + 4)
                    result[key] = unpack(value)
                return result
            if set(node) == {'$canary_literal'}:
                node = node['$canary_literal']
                if not isinstance(node, dict):
                    raise ValueError('Invalid encoded literal')
            account(sum(len(json.dumps(key, ensure_ascii=False).encode('utf-8')) + 4 for key in node))
            return {key: unpack(value) for key, value in node.items()}

        expanded, seen = [], set()
        result = None
        for entry in encoding['artifacts']:
            i = entry['index']
            if (type(i) is not int or not 0 <= i < len(artifacts) or i in seen
                    or entry['name'] not in ('canary-bundle.json', 'canary-research.json')
                    or artifacts[i]['name'] != entry['name'] or entry['style'] not in ('default', 'compact')):
                raise ValueError('Invalid encoded artifact descriptor')
            seen.add(i)
            decoded = unpack(parse(artifacts[i]['content']))
            expanded.append(json.dumps(decoded, ensure_ascii=False,
                **({'separators': (',', ':')} if entry['style'] == 'compact' else {})))
            if i == index:
                result = decoded
        check = {'artifacts': expanded}
        if encoding['view']:
            check['view'] = unpack(run['method_metadata']['canary_view'])
        if sha256(json.dumps(check, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()) != encoding['sha256']:
            raise ValueError('Preserved artifact reconstruction checksum mismatch')
        if result is None:
            result = parse(artifact['content'])  # The selected artifact was not reference encoded.
    if not isinstance(result, dict):
        raise ValueError('Preserved research artifact must be an object')
    return index, result


def context_ids(knowledge, identity):
    result, offset = set(), 0
    while True:
        page = knowledge.context(identity, limit=100, offset=offset)
        result.update(item['id'] for item in page['items'] if item['id'] in knowledge.by_id)
        if page['next_offset'] is None:
            return result
        offset = page['next_offset']


def export_state(knowledge, reference, *, repository, reference_pointer=None):
    if not isinstance(repository, str) or not repository.strip() or len(repository) > 2048:
        raise Invalid('Supply the selected repository identity (not inferred from package data)')
    if not isinstance(reference, str) or not reference:
        raise Invalid('Supply a question ID or persisted external reference')
    provenance = knowledge.knowledge['provenance']
    runs = {item['id']: (path, item) for path, item in provenance.items() if family(path) == 'submission'}
    receipts = {item['submission_id']: item for path, item in provenance.items() if family(path) == 'closure'}
    selected, direct_runs = set(), set()
    if reference_pointer is None:
        if reference not in knowledge.records['questions']:
            raise Invalid('Select a canonical question, or provide its persisted reference pointer')
        selected.update(context_ids(knowledge, reference))
        selection_kind = 'canonical_question'
    else:
        # Validate syntax even in an empty model. Absent fields simply do not match.
        try:
            pointer({}, reference_pointer)
        except KeyError:
            pass
        except (ValueError, IndexError, TypeError) as error:
            raise Invalid('Invalid external question reference pointer') from error
        for rid, (_, run) in runs.items():
            try:
                value = pointer(run, reference_pointer)
            except (KeyError, IndexError, ValueError, TypeError):
                continue
            if value == reference:
                direct_runs.add(rid)
                receipt = receipts[rid]
                selected.update(d['claim_id'] for d in receipt['claim_dispositions'] if d['claim_id'])
                selected.update(knowledge.state[p]['id'] for p in receipt['touched_files']
                                if family(p) in CANONICAL_ROOTS)
        if not direct_runs:
            raise Invalid('No preserved submission matches this exact external question reference')
        selection_kind = 'persisted_external_reference'
    # One existing context neighbourhood per seed claim. Do not walk the whole graph.
    for cid in sorted(selected.intersection(knowledge.records['claims'])):
        selected.update(context_ids(knowledge, cid))
    # Retain complete support/premise chains for the selected neighbourhood.
    pending = list(selected)
    while pending:
        identity = pending.pop()
        kind, record = knowledge.by_id[identity]
        linked = set(knowledge.groups[identity])
        if kind == 'claims':
            linked.update(record['evidence_ids'])
        elif kind == 'evidence':
            linked.update(record['premise_claim_ids'])
            linked.update(knowledge.source_ancestors(record['source_ids']))
        elif kind == 'graph':
            linked.update([record['from'], record['to']] + record['evidence_ids'])
        for item in linked - selected:
            selected.add(item); pending.append(item)
    grouped = {kind: selected.intersection(values) for kind, values in knowledge.records.items()}
    history = knowledge.provenance_for(grouped)
    # Zero-claim/rejected-only runs still contribute producer history to external questions.
    pending_runs = list(direct_runs)
    while pending_runs:
        rid = pending_runs.pop()
        path, run = runs[rid]
        history[path] = run
        for path, item in provenance.items():
            if item.get('submission_id') == rid:
                history[path] = item
        parent = run['parent_run_id']
        if parent is not None and runs[parent][0] not in history:
            pending_runs.append(parent)
    contributing = {item['id']: item for path, item in history.items() if family(path) == 'submission'}
    papers, coverage, findings = [], [], []
    question_texts = ([{'id': reference, 'text': knowledge.records['questions'][reference]['question'],
                       'basis': knowledge.knowledge['record_paths'][reference]}] if reference_pointer is None else
        [{'id': rid, 'text': runs[rid][1]['brief']['question'], 'basis': runs[rid][0] + '#/brief/question'}
         for rid in sorted(direct_runs) if runs[rid][1]['brief'] is not None])
    for sid in sorted(grouped['sources']):
        source = knowledge.records['sources'][sid]
        if source['kind'] != 'publication':
            continue
        uri = source['uri'] or ''
        doi = next((uri[len(prefix):] for prefix in ('https://doi.org/', 'http://doi.org/', 'doi:') if uri.startswith(prefix)), None)
        cited = any(sid in knowledge.records['evidence'][eid]['source_ids'] for eid in grouped['evidence'])
        papers.append({'submission_id': None, 'basis': knowledge.knowledge['record_paths'][sid],
            'paper_id': sid, 'doi': doi, 'url': source['uri'], 'reference': source, 'review_records': [],
            'stages': {'discovered': 'recorded_source', 'cited': 'recorded_evidence_link' if cited else 'unknown',
                       'retrieved': 'inspected_passage_only' if source['access'] == 'inspected' else 'not_retrieved',
                       'substantively_reviewed': 'unknown'},
            'limitations': ['Native source inspection does not establish a full-paper or substantive review.']})
    for rid, run in sorted(contributing.items()):
        try:
            index, artifact = research_artifact(run)
            anchor = runs[rid][0] + '#/result/artifacts/' + str(index) + '/content'
            if rid in direct_runs and isinstance(artifact.get('question'), str) and artifact['question']:
                question_texts.append({'id': rid, 'text': artifact['question'], 'basis': anchor + '#/question'})
            references = artifact.get('references', [])
            reviews = artifact.get('reviewed_papers', [])
            if (not isinstance(references, list) or not all(isinstance(r, dict) for r in references)
                    or not isinstance(reviews, list) or not all(isinstance(r, dict) for r in reviews)):
                raise ValueError('Invalid publication coverage arrays')
            # Keep observations per submission. Never deduplicate reviews by DOI or hash.
            selection = artifact.get('selection', {})
            if not isinstance(selection, dict):
                raise ValueError('Invalid preserved paper selection')
            selected_ids = selection.get('selected_for_review_ids', [])
            if not isinstance(selected_ids, list) or not all(isinstance(v, str) for v in selected_ids):
                raise ValueError('Invalid preserved selected paper IDs')
            run_papers = []
            for i, ref in enumerate(references):
                related = [r for r in reviews if r.get('work_id') == ref.get('id') and ref.get('id')]
                documented = [r for r in related if r.get('eligibility') in ('core', 'supporting')
                    and isinstance(r.get('passage_ids_read'), list) and r['passage_ids_read']
                    and all(isinstance(v, str) and v for v in r['passage_ids_read'])
                    and isinstance(r.get('investigated_sections'), list) and r['investigated_sections']
                    and all(isinstance(v, str) and v for v in r['investigated_sections'])
                    and isinstance(r.get('substantive_review_note'), str) and r['substantive_review_note'].strip()]
                preview = ref.get('preview_marker_detected') or ref.get('full_text_status') == 'preview_suspected'
                run_papers.append({'submission_id': rid, 'basis': anchor + '#/references/' + str(i),
                    'paper_id': ref.get('id') if isinstance(ref.get('id'), str) else None,
                    'doi': ref.get('doi') if isinstance(ref.get('doi'), str) else None,
                    'url': ref.get('url') if isinstance(ref.get('url'), str) else None,
                    'reference': ref, 'review_records': related,
                    'stages': {'discovered': 'recorded_reference',
                        'cited': 'producer_reported' if any(r.get('incorporated_in_output') is True for r in related) else 'unknown',
                        'retrieved': 'producer_reported' if isinstance(ref.get('fresh_download_at'), str) and ref['fresh_download_at'] and not preview else 'unknown',
                        'substantively_reviewed': 'producer_reported' if documented and ref.get('id') in selected_ids
                            and not preview else 'unknown'},
                    'limitations': ['Producer declarations; review depth and source independence are not independently established.']})
            # Orphan reviews remain visible instead of disappearing in an identity join.
            known = {ref['id'] for ref in references if isinstance(ref.get('id'), str)}
            orphan = [r for r in reviews if r.get('work_id') not in known]
            coverage.append({'submission_id': rid, 'status': 'preserved_producer_report',
                             'artifact': anchor, 'unmatched_review_records': orphan})
            papers.extend(run_papers)
            findings.append({'submission_id': rid, 'basis': anchor,
                             'fields': {key: artifact[key] for key in ('contradictions', 'gaps', 'caveats', 'residue', 'next_questions', 'scope_note') if key in artifact}})
        except (ValueError, Invalid, KeyError, IndexError, TypeError, RecursionError, OverflowError):
            coverage.append({'submission_id': rid, 'status': 'unknown',
                             'reason': 'Missing, unsupported or invalid preserved research artifact; raw submission retained.'})
    return copy.deepcopy({'schema_version': '1.0', 'kind': 'resolvent.research-state',
        'repository': repository, 'build': dict(knowledge.build), 'model_sha256': knowledge.model_sha256,
        'question': {'reference': reference, 'recorded_texts': question_texts},
        'selection': {'kind': selection_kind, 'reference': reference, 'reference_pointer': reference_pointer,
                      'matched_submission_ids': sorted(direct_runs), 'rule': 'existing_context_neighbourhood_and_support_chains'},
        'canonical': {kind: {i: knowledge.records[kind][i] for i in sorted(grouped[kind])} for kind in CANONICAL_ROOTS},
        'assessments': {cid: knowledge.view(cid, 0, 100, 0)['current_assessment'] for cid in sorted(grouped['claims'])},
        'producer_material': history, 'contributing_submission_ids': sorted(contributing),
        'publications': papers, 'review_coverage': coverage, 'producer_findings': findings,
        'coverage': {'exhaustive': False, 'omissions': ['Unlinked questions, graph neighbourhoods beyond seed claims and material absent from the selected revision.',
            'No semantic contradiction discovery or verification of producer research was performed.'],
            'omitted_record_counts': {kind: len(knowledge.records[kind]) - len(grouped[kind]) for kind in CANONICAL_ROOTS},
            'unknown_paper_coverage': 'Absence of a review record never means a paper was not reviewed.',
            'source_identity': 'Original source IDs, URIs, locators, access and hashes remain in canonical/producer records; hashes do not establish independence.'}})


def research_state(knowledge, reference, *, repository, reference_pointer=None, complete=False, offset=0, max_bytes=32768):
    if type(complete) is not bool:
        raise Invalid('complete must be boolean')
    state = export_state(knowledge, reference, repository=repository, reference_pointer=reference_pointer)
    if complete:
        if offset != 0:
            raise Invalid('Complete export cannot resume at an offset')
        return state
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2)
    return text_page(knowledge, 'research_state', text, offset=offset, max_bytes=max_bytes,
                       include_truncated=True,
                       research_state_schema='1.0', state_sha256=sha256(text.encode()))
