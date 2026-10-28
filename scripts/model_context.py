"""Bounded local model data for externally implemented agent behaviors."""
from __future__ import annotations

import copy
import json

from scripts.build_knowledge import json_bytes
from scripts.model import Invalid

MAX_BYTES = 32 * 1024


def bounded_page(knowledge, operation, items, *, offset=0, limit=20, max_bytes=MAX_BYTES, **metadata):
    from scripts.query_knowledge import bound
    bound(limit, 1, 100, 'limit')
    bound(offset, 0, 2**63-1, 'offset')
    bound(max_bytes, 1024, MAX_BYTES, 'max_bytes')
    result = knowledge.envelope(operation, **metadata, items=[], total=len(items), offset=offset,
                                next_offset=None, truncated=False)
    for item in items[offset:offset+limit]:
        result['items'].append(copy.deepcopy(item))
        end = offset + len(result['items'])
        result.update(next_offset=end if end < len(items) else None, truncated=end < len(items))
        if len(json_bytes(result)) > max_bytes:
            result['items'].pop()
            end = offset + len(result['items'])
            result.update(next_offset=end, truncated=True)
            break
    if not result['items'] and offset < len(items):
        raise Invalid('Requested page cannot fit one context item; use a passage read or larger byte limit')
    if len(json_bytes(result)) > max_bytes:
        raise Invalid('Context metadata exceeds response bound')
    return result


def card(kind, record):
    text = next((record[k] for k in ('statement', 'question', 'title', 'summary', 'reason') if record.get(k)), '')
    return {'id':record['id'], 'kind':kind, 'preview':text[:240], 'preview_truncated':len(text)>240,
            **{k:record[k] for k in ('class','uncertainty','state','date','access','independent','type','from','to','spec') if k in record}}


def candidates(knowledge, text='', *, kind='claims', offset=0, limit=20, max_bytes=MAX_BYTES, grouped=False):
    from scripts.query_knowledge import tokens
    if kind not in knowledge.records:
        raise Invalid('Unknown candidate record kind')
    words = set(tokens(text))
    results = []
    for identity, record in knowledge.records[kind].items():
        fields = ('statement', 'question', 'summary', 'title', 'uri', 'locator', 'excerpt', 'reason')
        corpus = ' '.join(record[k] for k in fields if isinstance(record.get(k), str))
        if kind == 'sources':
            corpus += ' ' + json.dumps(record.get('ancestry',{}),ensure_ascii=False,sort_keys=True)
        overlap = words.intersection(tokens(corpus))
        if words and not overlap:
            continue
        entry = card(kind, record)
        entry.update(relevance=len(overlap), reasons=['keyword_overlap'] if words else ['record_enumeration'])
        if text and ' '.join(text.split()) == ' '.join(next((record[k] for k in ('statement','question','summary','title') if record.get(k)), '').split()):
            entry['reasons'].append('exact_text_only_not_identity')
        results.append(entry)
    results.sort(key=lambda item:(-item['relevance'],item['id']))
    if grouped:
        selected,seen=[],set()
        for entry in results:
            group=knowledge.groups[entry['id']]
            if group[0] not in seen:
                seen.add(group[0]);selected.append(dict(entry,group_id=group[0],member_count=len(group)))
        results=selected
    return bounded_page(knowledge, 'candidates', results, kind=kind, query_preview=text[:240],
                        ranking='keyword_relevance_only', offset=offset, limit=limit, max_bytes=max_bytes)


def context(knowledge, record_id, *, purpose='comparison', offset=0, limit=20, max_bytes=MAX_BYTES):
    if record_id not in knowledge.by_id:
        raise Invalid('Unknown context record')
    if purpose not in ('comparison', 'linkage', 'reassessment'):
        raise Invalid('Unknown context purpose')
    kind, record = knowledge.by_id[record_id]
    ids = {record_id}
    members = knowledge.groups[record_id]
    ids.update(members)
    # Expand a single model neighbourhood, retaining raw endpoints and joint premises.
    for member in members:
        member_kind, item = knowledge.by_id[member]
        if member_kind == 'claims':
            ids.update(item['evidence_ids'])
            reverse = knowledge.knowledge['reverse_links']['claims'][member]
            ids.update(reverse['incoming_connector_ids'] + reverse['outgoing_connector_ids'] + reverse['question_ids'])
        elif member_kind == 'sources':
            ids.update(knowledge.knowledge['reverse_links']['sources'][member]['evidence_ids'])
        elif member_kind == 'evidence':
            ids.update(item['source_ids'] + item['premise_claim_ids'] + item['claim_ids'])
        elif member_kind == 'questions':
            ids.update(item['claim_ids'])
        elif member_kind == 'graph':
            ids.update([item['from'],item['to']] + item['evidence_ids'])
    for identity in list(ids):
        item_kind, item = knowledge.by_id[identity]
        if item_kind == 'evidence':
            ids.update(knowledge.source_ancestors(item['source_ids']))
            ids.update(item['premise_claim_ids'])
        elif item_kind == 'graph':
            ids.update([item['from'],item['to']] + item['evidence_ids'])
    items = [card(*knowledge.by_id[v]) for v in sorted(ids, key=lambda v:(v!=record_id,v))]
    # Assessment and comparison bodies are individually expandable through passage().
    for ref, op in sorted(knowledge.operations.items()):
        if set(op['subject_ids']).intersection(members):
            items.append({'id':ref,'kind':op['kind'],'preview':op['reason'][:240],
                          'preview_truncated':len(op['reason'])>240})
    return bounded_page(knowledge, 'context', items, record_id=record_id, purpose=purpose,
                        offset=offset,limit=limit,max_bytes=max_bytes)


def passage(knowledge, record_id, *, field=None, offset=0, max_bytes=MAX_BYTES):
    from scripts.query_knowledge import bound
    bound(offset,0,2**63-1,'offset');bound(max_bytes,1024,MAX_BYTES,'max_bytes')
    record = knowledge.by_id[record_id][1] if record_id in knowledge.by_id else knowledge.operations.get(record_id)
    if record is None:
        raise Invalid('Unknown passage record')
    if field is None:
        text = json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2)
    else:
        text = record.get(field)
        if not isinstance(text,str):
            raise Invalid('Passage field must be a native text field')
    end = min(len(text),offset+max_bytes)
    def response(end):
        return knowledge.envelope('passage',record_id=record_id,field=field,offset=offset,
                                  total_chars=len(text),next_offset=end if end<len(text) else None,
                                  text=text[offset:end])
    low, high = offset, max(offset,end)
    while low<high:
        middle=(low+high+1)//2
        if len(json_bytes(response(middle)))<=max_bytes:
            low=middle
        else:
            high=middle-1
    if low==offset and offset<len(text):
        raise Invalid('Passage metadata exceeds response bound')
    result=response(low)
    if len(json_bytes(result))>max_bytes:
        raise Invalid('Passage metadata exceeds response bound')
    return result


def assessment_history(knowledge, record_id, *, offset=0, limit=20, max_bytes=MAX_BYTES):
    if record_id not in knowledge.records['claims']:
        raise Invalid('Assessment history requires a claim ID')
    items=copy.deepcopy(knowledge.supplied_assessments[record_id])
    for ref,op in sorted(knowledge.operations.items()):
        if op['kind']=='reassessment' and record_id in op['subject_ids']:
            items.append({'id':ref,'kind':'reassessment','uncertainty':op['uncertainty'],
                          'previous_uncertainty':op['previous_uncertainty'][record_id],
                          'predecessor':op['predecessors'][record_id],'reason_preview':op['reason'][:240]})
    return bounded_page(knowledge,'assessments',items,record_id=record_id,
                        current_uncertainty=knowledge.records['claims'][record_id]['uncertainty'],
                        current_assessment=knowledge.current_assessments.get(record_id),
                        offset=offset,limit=limit,max_bytes=max_bytes)


def changes(knowledge, before_package, *, offset=0, limit=20, max_bytes=MAX_BYTES):
    from pathlib import Path
    from scripts.query_knowledge import Knowledge
    from scripts.change_impact import changes as record_changes
    before=Knowledge(Path(before_package))
    items=[]
    for change in record_changes(before.records,knowledge.records):
        record=change['after'] or change['before']
        items.append(dict(card(change['group'],record),change=change['operation'],changed_fields=change['changed_fields']))
    for ref,op in sorted(knowledge.operations.items()):
        if ref not in before.operations:
            items.append({'id':ref,'kind':op['kind'],'change':'added','preview':op['reason'][:240]})
    return bounded_page(knowledge,'changes',items,before_build=before.build,
                        offset=offset,limit=limit,max_bytes=max_bytes)
