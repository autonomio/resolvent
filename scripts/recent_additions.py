"""The recent-maintenance window and its complete comparison input; no judgments."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import json
from pathlib import Path
import re

from scripts.build_knowledge import git
from scripts.model import CANONICAL_ROOTS, Invalid, digest, family
from scripts.temporal import point, temporal_scope

RECORD_PATH = re.compile(r'(?:claims|evidence|sources|graph|questions|maintenance)/([CESRQM]-[0-9a-f]{32})\.yaml')
WINDOW_FIELDS = ('start', 'previous_workset_id', 'from_revision', 'from_committed_at', 'to_committed_at', 'hours')


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def committed(seconds: int) -> str:
    return utc(datetime.fromtimestamp(seconds, timezone.utc))


def window(repo: Path, revision: str, maintenance, *, hours: int = 24, at=None) -> dict:
    """Start at the last completed recent workset's base, else `hours` before `at`.

    Both starts are revisions on the selected revision's first-parent history; recorded
    Git committer time is used only when no recent workset has completed. A late or
    failed night therefore loses nothing and never reaches further back. History that
    starts after the cutoff opens the window at the empty model.
    """
    if type(hours) is not int or not 1 <= hours <= 8760:
        raise Invalid('Recent window hours must be between 1 and 8760')
    if at is None:
        at = datetime.now(timezone.utc)
    elif isinstance(at, str):
        kind, at = point(at)
        if kind != 'instant':
            raise Invalid('Recent window time requires a full timestamp with timezone')
    if not isinstance(at, datetime) or at.tzinfo is None:
        raise Invalid('Recent window time requires an explicit timezone')
    if git(repo, 'rev-parse', '--is-shallow-repository').decode().strip() != 'false':
        raise Invalid('Recent windows need complete local history, not a shallow clone')
    commit = git(repo, 'rev-parse', '--verify', '--end-of-options', revision + '^{commit}').decode().strip()
    history = [(sha, int(seconds)) for sha, seconds in
               (line.split() for line in git(repo, 'log', '--first-parent', '--format=%H %ct', commit).decode().splitlines())]
    bases = {}
    for record in maintenance:
        if record['status'] == 'completed' and 'window' in record:
            bases.setdefault(record['base_commit'], []).append(record['id'])
    start = next((item for item in history if item[0] in bases), None)
    cutoff = None
    if start is None:
        cutoff = at - timedelta(hours=hours)
        start = next((item for item in history if item[1] <= cutoff.timestamp()), None)
    return {'start': 'last_completed_recent_workset' if cutoff is None else 'hours',
            'previous_workset_id': min(bases[start[0]]) if cutoff is None else None,
            'from_revision': start[0] if start else None,
            'from_committed_at': committed(start[1]) if start else None,
            'to_revision': commit, 'to_committed_at': committed(history[0][1]), 'hours': hours,
            'at': utc(at), 'cutoff': utc(cutoff) if cutoff is not None else None}


def recorded_ids(repo: Path, revision: str | None) -> set[str]:
    """Canonical and maintenance IDs in a revision's tree, read from Git objects without a checkout."""
    if revision is None:
        return set()
    listing = git(repo, 'ls-tree', '-r', '-z', '--name-only', '--full-tree', revision, '--',
                  *CANONICAL_ROOTS, 'maintenance')
    return {match.group(1) for name in listing.split(b'\0')
            if (match := RECORD_PATH.fullmatch(name.decode('utf-8', 'replace')))}


def recent(knowledge, repo=Path('.'), *, hours=24, at=None, to=None, overlap_limit=20) -> dict:
    """Every claim added in the window and what it must be compared with, in one response.

    `to` ends the window at an ancestor of the package revision, such as a recent
    workset's base_commit, so a later package still returns exactly that workset.
    """
    from scripts.query_knowledge import bound, tokens
    bound(overlap_limit, 0, 1000, 'overlap_limit')
    repo = Path(repo)
    records, reverse = knowledge.records, knowledge.knowledge['reverse_links']['claims']
    claims, evidence, graph = records['claims'], records['evidence'], records['graph']
    provenance, groups = knowledge.knowledge['provenance'], knowledge.groups
    end = revision = knowledge.build['source_revision']
    if to is not None:
        end = git(repo, 'rev-parse', '--verify', '--end-of-options', to + '^{commit}').decode().strip()
        try:
            git(repo, 'merge-base', '--is-ancestor', end, revision)
        except Invalid:
            raise Invalid('The window must end at the package revision or one of its ancestors') from None
    present = recorded_ids(repo, end)
    span = window(repo, end, [item for path, item in provenance.items()
                              if family(path) == 'maintenance' and item['id'] in present], hours=hours, at=at)
    in_window = present - recorded_ids(repo, span['from_revision'])
    added = sorted(cid for cid in claims if cid in in_window)
    targets = [cid for cid in sorted(claims) if claims[cid]['state'] == 'active']
    replaced = {op['supersedes'] for op in knowledge.operations.values() if op['kind'] == 'comparison' and op['supersedes']}
    by_pair, by_claim = {}, {}
    for ref, op in sorted(knowledge.operations.items()):
        if op['kind'] == 'comparison':
            item = {'id': ref, 'subject_ids': list(op['subject_ids']), 'outcome': op['outcome'], 'current': ref not in replaced}
            by_pair.setdefault(frozenset(op['subject_ids']), []).append(item)
            for subject in op['subject_ids']:
                by_claim.setdefault(subject, []).append(item)
    admissions = {}
    for path, item in sorted(provenance.items()):
        if family(path) == 'closure':
            for disposition in item['claim_dispositions']:
                if disposition['claim_id'] is not None:
                    admissions.setdefault(disposition['claim_id'], []).append({
                        'closure_id': item['id'], 'submission_id': item['submission_id'],
                        'candidate_id': disposition['candidate_id'], 'disposition': disposition['disposition']})

    def direct_sources(cid):
        return sorted({sid for eid in claims[cid]['evidence_ids'] for sid in evidence[eid]['source_ids']})

    # Declared identity only: the record or its accepted group, a declared ancestor, or a declared content digest.
    source_keys, question_keys, words = {}, {}, {}
    for cid in set(targets) | set(added):
        source_keys[cid] = {}
        for sid in knowledge.source_ancestors(direct_sources(cid)):
            content = records['sources'][sid].get('ancestry', {}).get('content_sha256')
            source_keys[cid][sid] = {'source:' + groups[sid][0]} | ({'sha256:' + content} if content else set())
        question_keys[cid] = {qid: {groups[qid][0]} for qid in reverse[cid]['question_ids']}
        words[cid] = set(tokens(claims[cid]['statement']))

    def shared(keys, a, b):
        common = set().union(*keys[a].values()) & set().union(*keys[b].values())
        return sorted({item for side in (a, b) for item, values in keys[side].items() if values & common})

    def connector(rid):
        return {'record': copy.deepcopy(graph[rid]), 'sha256': digest(graph[rid])}

    def incident(cid):
        return sorted(set(reverse[cid]['incoming_connector_ids'] + reverse[cid]['outgoing_connector_ids']))

    def summary(cid):
        claim = claims[cid]
        return {'id': cid, 'statement': claim['statement'], 'class': claim['class'],
                'temporal_scope': json.loads(temporal_scope(claim.get('valid_time'))),
                'uncertainty': claim['uncertainty'], 'state': claim['state'],
                'evidence_ids': list(claim['evidence_ids']), 'source_ids': direct_sources(cid),
                'question_ids': list(reverse[cid]['question_ids']), 'equivalence_group': list(groups[cid]),
                'current_assessment': knowledge.current_assessments.get(cid), 'added_in_window': cid in in_window}

    def between(a, b):
        return {'connectors': [connector(rid) for rid in incident(a) if {graph[rid]['from'], graph[rid]['to']} == {a, b}],
                'comparisons': copy.deepcopy(by_pair.get(frozenset((a, b)), [])),
                'premise_evidence_ids': sorted(eid for x, y in ((a, b), (b, a)) for eid in claims[x]['evidence_ids']
                                               if y in evidence[eid]['premise_claim_ids'])}

    entries = []
    for cid in added:
        structural, wording = [], []
        for other in targets:
            if other == cid:
                continue
            match = (other, shared(source_keys, cid, other), shared(question_keys, cid, other),
                     sorted(words[cid] & words[other]))
            if match[1] or match[2]:
                structural.append(match)  # Shared sources and questions are never capped.
            elif match[3]:
                union = len(words[cid] | words[other])
                wording.append((-Fraction(len(match[3]), union), -len(match[3]), other, match))
        wording.sort()
        compare_with = []
        for other, sources, questions, terms in structural + [item[3] for item in wording[:overlap_limit]]:
            reasons = [name for name, value in (('shared_source', sources), ('same_question', questions),
                                                ('wording_overlap', terms)) if value]
            compare_with.append(dict(summary(other), reasons=reasons, shared_source_ids=sources,
                                     shared_question_ids=questions, shared_terms=terms, links=between(cid, other)))
        claim = claims[cid]
        source_ids = sorted(knowledge.source_ancestors(direct_sources(cid)))
        question_ids = reverse[cid]['question_ids']
        entry = summary(cid)
        entry.update(valid_time=copy.deepcopy(claim.get('valid_time')), admissions=admissions.get(cid, []),
                     evidence=[copy.deepcopy(evidence[eid]) for eid in claim['evidence_ids']],
                     sources=[copy.deepcopy(records['sources'][sid]) for sid in source_ids],
                     questions=[copy.deepcopy(records['questions'][qid]) for qid in question_ids],
                     added_in_window_ids=sorted(v for v in claim['evidence_ids'] + source_ids + question_ids
                                                if v in in_window),
                     connectors=[connector(rid) for rid in incident(cid)],
                     comparisons=copy.deepcopy(by_claim.get(cid, [])), compare_with=compare_with,
                     wording_overlap={'matches': len(wording), 'included': min(len(wording), overlap_limit),
                                      'omitted': max(0, len(wording) - overlap_limit)})
        entries.append(entry)
    return knowledge.envelope(
        'recent', window=span,
        interpretation=('Added claims are absent from the window start. compare_with cues are declared source '
                        'identity, question membership and statement keyword overlap; they establish no identity, '
                        'support or truth, and no semantic matching is performed.'),
        wording_overlap_limit=overlap_limit,
        wording_overlap_ranking=('claims related only by wording: Jaccard overlap of distinct statement words, '
                                 'then shared-word count, then claim ID'),
        decisions={'expected_model_sha256': knowledge.model_sha256, 'reviewed_claim_ids': added},
        added_total=len(added), added=entries)
