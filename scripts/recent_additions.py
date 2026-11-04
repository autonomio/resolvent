"""The recent-maintenance window, its complete comparison input and its gate; no judgments."""
from __future__ import annotations

from collections import Counter
import copy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import json
from pathlib import Path
import re

from scripts.build_knowledge import git
from scripts.model import CANONICAL_ROOTS, Invalid, digest, fail, family, indexes
from scripts.temporal import point, temporal_scope

RECORD_PATH = re.compile(r'(?:claims|evidence|sources|graph|questions|maintenance)/([CESRQM]-[0-9a-f]{32})\.yaml')
WINDOW_FIELDS = ('start', 'previous_workset_id', 'from_revision', 'from_committed_at', 'to_committed_at', 'hours',
                 'new_source_ids', 'question_ids')


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def committed(seconds: int) -> str:
    return utc(datetime.fromtimestamp(seconds, timezone.utc))


def window(repo: Path, revision: str, maintenance, *, hours: int = 24, at=None) -> dict:
    """Start at the last completed recent workset's base, else `hours` before `at`.

    Both starts are revisions on the selected revision's first-parent history. Once a
    recent workset has completed, its base is a recorded start: a late, failed or
    unmerged night loses nothing, and the window never reaches further back. Until then
    nothing records a start, so the window is the `hours` before `at` by Git committer
    time. History that starts after that cutoff opens the window at the empty model.
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


def selection(repo: Path, revision: str, maintenance, questions, *, hours: int = 24, at=None) -> tuple[dict, set[str]]:
    """The window as of `revision` and every record ID it added, from Git objects only.

    Only maintenance and question records present at `revision` count, so a later state
    reproduces the same selection. The window also records the sources it added and the
    questions present at its end that hold an added claim.
    """
    commit = git(repo, 'rev-parse', '--verify', '--end-of-options', revision + '^{commit}').decode().strip()
    present = recorded_ids(repo, commit)
    span = window(repo, commit, [record for record in maintenance if record['id'] in present], hours=hours, at=at)
    added = present - recorded_ids(repo, span['from_revision'])
    claims = {value for value in added if value.startswith('C-')}
    span.update(new_source_ids=sorted(value for value in added if value.startswith('S-')),
                question_ids=sorted(question['id'] for question in questions
                                    if question['id'] in present and claims.intersection(question['claim_ids'])))
    return span, added


def pass_scope(record: dict, operations: list, claims: dict) -> None:
    """Recent-mode rules: every operation has an added claim, and grades move only to settle a merge.

    A reassessment may name an added claim or the claim it was found equivalent to in the
    same pass, and only when that equivalent pair had different grades before the pass.
    """
    added = set(record['claim_ids'])
    settles = set()
    for op in operations:
        subjects = op['subject_ids']
        if (op.get('kind') == 'comparison' and op.get('outcome') == 'equivalent' and added.intersection(subjects)
                and len(subjects) == 2 and all(subject in claims for subject in subjects)
                and claims[subjects[0]]['uncertainty'] != claims[subjects[1]]['uncertainty']):
            settles.update(subjects)
    for op in operations:
        if op.get('kind') == 'reassessment':
            fail(set(op['subject_ids']) <= settles, 'A recent pass reassesses only an added claim or its equivalent, '
                 'to settle a merge that joined different grades')
        else:
            fail(bool(added.intersection(op['subject_ids'])), 'Every operation in a recent pass needs an added claim as a subject')


def verify_pass(root: Path, old: dict, current: dict, data_changes: set[str], reports: dict) -> None:
    """The gate for a change that completes a recent pass, which merges on green CI alone.

    `reports` maps each changed nightly brief path to its (base, proposed) bytes.
    """
    from scripts.nightly_brief import brief_path, verify
    for path, (before, after) in sorted(reports.items()):
        fail(before is None and after is not None, 'Nightly briefs are immutable once merged: ' + path)
    passes = sorted(path for path in data_changes if path in current and family(path) == 'maintenance'
                    and current[path]['status'] == 'completed' and 'window' in current[path])
    if not passes:
        fail(not reports, 'A nightly brief belongs to its completed recent pass in the same change: ' +
             ', '.join(sorted(reports)))
        return
    fail(len(passes) == 1, 'Complete one recent pass per change')
    record = current[passes[0]]
    location = brief_path(record)
    fail(set(reports) == {location}, 'A completed recent pass adds exactly its nightly brief ' + location)
    try:
        top = Path(git(root, 'rev-parse', '--show-toplevel').decode().strip())
        shallow = git(root, 'rev-parse', '--is-shallow-repository').decode().strip()
    except Invalid as error:
        raise Invalid('A recent pass is verified against the Git history of its checkout: ' + str(error)) from None
    fail(top.is_dir() and top.samefile(root), 'A recent pass is verified against the Git history of its own checkout')
    fail(shallow == 'false', 'A recent pass is verified against complete Git history, not a shallow clone')
    maintenance = [item for path, item in current.items() if family(path) == 'maintenance']
    questions = [item for path, item in current.items() if family(path) == 'questions']
    span, added = selection(root, record['base_commit'], maintenance, questions,
                            hours=record['window']['hours'], at=record['created_at'])
    fail(span['to_revision'] == record['base_commit'] and record['window'] == {key: span[key] for key in WINDOW_FIELDS}
         and record['claim_ids'] == sorted(value for value in added if value.startswith('C-')),
         'A recent workset must be exactly the window Git history gives for its base_commit and created_at')
    try:
        git(root, 'merge-base', '--is-ancestor', record['base_commit'], 'HEAD')
    except Invalid:
        raise Invalid("A recent workset's base_commit must be in the history of the proposed change") from None
    operations = record['model_operations']
    reassessed = {subject for op in operations if op['kind'] == 'reassessment' for subject in op['subject_ids']}
    linked = {op['record']['id'] for op in operations if op['kind'] == 'linkage'}
    for path in sorted(data_changes - {passes[0]}):
        before, after = old.get(path), current.get(path)
        if family(path) == 'claims' and before and after and after['id'] in reassessed:
            fail({k: v for k, v in before.items() if k != 'uncertainty'} == {k: v for k, v in after.items() if k != 'uncertainty'},
                 'A recent pass changes a claim only by reassessing its grade: ' + path)
        else:
            fail(family(path) == 'graph' and after is not None and after['id'] in linked,
                 'A recent pass changes only its maintenance record, its nightly brief and the results of its '
                 'recorded operations: ' + path)
    pass_scope(record, operations, indexes(old).get('claims', {}))
    try:
        text = reports[location][1].decode('utf-8').replace('\r\n', '\n')
    except UnicodeError:
        raise Invalid('Nightly brief is not UTF-8: ' + location) from None
    verify(record, text, {item['id'] for item in current.values()})


def shape(knowledge) -> dict:
    """The whole model as generated counts over active claims: no statement or judgment."""
    claims, evidence, groups = knowledge.records['claims'], knowledge.records['evidence'], knowledge.groups
    active = {cid for cid, claim in claims.items() if claim['state'] == 'active'}
    per_question, per_source = {}, {}
    for qid, question in knowledge.records['questions'].items():
        per_question.setdefault(groups[qid][0], set()).update(active.intersection(question['claim_ids']))
    for cid in active:
        for sid in {sid for eid in claims[cid]['evidence_ids'] for sid in evidence[eid]['source_ids']}:
            per_source.setdefault(groups[sid][0], set()).add(cid)
    grades = Counter(claims[cid]['uncertainty'] for cid in active)
    disputed = {groups[cid][0] for cid in active
                if len({claims[member]['uncertainty'] for member in groups[cid] if member in active}) > 1}
    ranked = sorted(per_source.items(), key=lambda item: (-len(item[1]), item[0]))
    return {
        'claims': len(active),
        'claims_per_question': {ref: len(ids) for ref, ids in sorted(per_question.items())},
        'claims_without_question': len(active - set().union(*per_question.values())),
        'grade_spread': {grade: grades[grade] for grade in ('low', 'medium', 'high')},
        'disputed_groups': len(disputed),
        'source_concentration': {
            'cited_sources': len(per_source),
            'largest': [{'source_id': ref, 'claims': len(ids)} for ref, ids in ranked[:10]],
            'claims_citing_largest': len(set().union(*(ids for _, ids in ranked[:10]))),
            'sources_by_claim_count': [{'claims': count, 'sources': number} for count, number in
                                       sorted(Counter(len(ids) for ids in per_source.values()).items())]}}


def recent(knowledge, repo=Path('.'), *, hours=24, at=None, to=None, overlap_limit=20) -> dict:
    """Every claim added in the window and what it must be compared with, in one response.

    `to` ends the window at an ancestor of the package revision, such as a recent
    workset's base_commit, so a later package still returns exactly that workset.
    """
    from scripts.query_knowledge import bound, tokens
    from scripts.nightly_brief import brief_path
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
    maintenance = [item for path, item in provenance.items() if family(path) == 'maintenance']
    span, in_window = selection(repo, end, maintenance, records['questions'].values(), hours=hours, at=at)
    added = sorted(cid for cid in claims if cid in in_window)
    previous_brief = None
    if span['previous_workset_id'] is not None:
        prior = next(item for item in maintenance if item['id'] == span['previous_workset_id'])
        try:
            previous_brief = git(repo, 'show', f'{end}:{brief_path(prior)}').decode('utf-8').replace('\r\n', '\n')
        except (Invalid, UnicodeError):
            raise Invalid('The previous recent pass lacks a readable nightly brief') from None
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
                        'support or truth, and no semantic matching is performed. shape counts the whole model and '
                        'previous_brief is the last nightly brief as written; both serve only the brief\'s last section.'),
        wording_overlap_limit=overlap_limit,
        wording_overlap_ranking=('claims related only by wording: Jaccard overlap of distinct statement words, '
                                 'then shared-word count, then claim ID'),
        decisions={'expected_model_sha256': knowledge.model_sha256, 'reviewed_claim_ids': added,
                   'nightly_brief': {'what_moved': '', 'course': ''}},
        shape=shape(knowledge), previous_brief=previous_brief,
        added_total=len(added), added=entries)
