#!/usr/bin/env python3
"""Deterministic information ledger over canonical records (advisory, read-only).

Arithmetic over reviewed record structure only: no model calls, no wall clock, no
interpretation of text. It measures the observation base a model rests on and how
each change moved it. It does not measure truth. See docs/INFORMATION.md.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit

import yaml

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.answers import admitted_set, capacity, grid
from scripts.model import MAX_FILE_BYTES, Invalid, StrictLoader, read_data

LEDGER_VERSION = '1.2'
GROUPS = ('claims', 'evidence', 'sources', 'graph', 'questions')
# Closures and completed maintenance carry the repository's recorded model judgments.
JUDGMENT_ROOTS = ('briefs/closed', 'maintenance')
# A record's fixed location: one YAML file directly inside its folder.
RECORD_PATH = re.compile(rb'(?:claims|evidence|sources|graph|questions|maintenance|briefs/closed)/[^/]+\.yaml')
# A source kind fixes what sort of thing stands at the origin. It is never a quality rating.
STRATA = {'publication': 'observational', 'web': 'observational',
          'conversation': 'testimonial', 'interview': 'testimonial',
          'simulation': 'generated', 'model': 'generated', 'reasoning': 'generated'}
STRATUM_ORDER = ('observational', 'testimonial', 'generated', 'unclassified')
IDENTITY_BASES = ('sha256', 'uri', 'title', 'source')
CUE_THRESHOLD = Fraction(1, 2)
EMPTY = frozenset()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def exact(value) -> dict:
    """A rational is reported exactly; the decimal is a rounded reading aid."""
    value = Fraction(value)
    return {'exact': f'{value.numerator}/{value.denominator}', 'approx': round(float(value), 6)}


def origin_key(source: dict) -> tuple[str, str]:
    """Identity of a terminal source, from declared metadata only.

    Declared content digest, else normalized address, else the record itself.
    Titles alone do not identify a source.
    """
    stratum = STRATA.get(source.get('kind') or '', 'unclassified')
    digest = (source.get('ancestry') or {}).get('content_sha256')
    if digest:
        return stratum, 'sha256:' + digest
    uri = source.get('uri')
    if uri:
        try:
            parts = urlsplit(uri)
            if parts.scheme.lower() in ('http', 'https') and parts.netloc:
                uri = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ''))
        except ValueError:
            pass  # An unparseable address is kept verbatim, never guessed.
        return stratum, 'uri:' + uri
    return stratum, 'source:' + source['id']


def source_origins(sources: dict) -> dict[str, frozenset]:
    """Map every source to the origins at the end of its declared ancestry."""
    result = {}
    for sid in sources:
        seen, pending, terminal = {sid}, [sid], set()
        while pending:
            current = sources[pending.pop()]
            parents = [parent for parent in (current.get('ancestry') or {}).get('parent_source_ids', [])
                       if parent in sources]
            if not parents:
                terminal.add(origin_key(current))
            for parent in parents:
                if parent not in seen:
                    seen.add(parent)
                    pending.append(parent)
        result[sid] = frozenset(terminal)
    return result


def collect_operations(provenance) -> dict:
    """Recorded model judgments (scripts/model_operations.py), keyed as record#local id."""
    found = {}
    for record in provenance:
        if not isinstance(record, dict) or record.get('status', 'completed') != 'completed':
            continue
        for op in record.get('model_operations') or []:
            found[f"{record['id']}#{op['id']}"] = op
    return found


def collect_reviews(provenance) -> dict:
    """Count each claim reviewed by a completed maintenance record or admission closure once per record."""
    reviews = {}
    for record in provenance:
        if not isinstance(record, dict):
            continue
        record_id = record.get('id', '')
        if record_id.startswith('M-') and record.get('status') == 'completed':
            subjects = set(record.get('reviewed_claim_ids') or [])
        elif record_id.startswith('BC-'):
            subjects = set()
        else:
            continue
        subjects.update(claim_id for op in record.get('model_operations') or []
                        if op['kind'] == 'reassessment' for claim_id in op['subject_ids'])
        if subjects or record_id.startswith('M-'):
            reviews[record_id] = sorted(subjects)
    return reviews


def current_comparisons(records: dict) -> dict[tuple, str]:
    """The standing reviewed outcome for each compared pair: equivalent, overlap, distinct or unresolved."""
    ops = records.get('operations') or {}
    replaced = {op.get('supersedes') for op in ops.values() if op.get('kind') == 'comparison' and op.get('supersedes')}
    return {tuple(sorted(op['subject_ids'])): op['outcome'] for ref, op in sorted(ops.items())
            if op.get('kind') == 'comparison' and ref not in replaced}


def equivalence_roots(records: dict, members) -> dict[str, str]:
    """Group the given records by the repository's own standing `equivalent` judgments."""
    parent = {member: member for member in members}

    def root(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    for (left, right), outcome in current_comparisons(records).items():
        if outcome == 'equivalent' and left in parent and right in parent:
            a, b = root(left), root(right)
            parent[max(a, b)] = min(a, b)
    return {member: root(member) for member in parent}


def active(records: dict) -> dict:
    return {record_id: record for record_id, record in records.items() if record.get('state') == 'active'}


class Measure:
    """The support structure of one state: claims, origins, and which origin bears on which claim.

    Connectors are measured apart. Their evidence usually repeats their endpoints'
    evidence, so counting it with claims would let relationship records dilute or
    inflate the observation base without any new observation.
    """

    def __init__(self, records: dict):
        self.records = {group: records.get(group, {}) for group in GROUPS}
        self.records['operations'] = records.get('operations') or {}
        evidence = self.records['evidence']
        by_source = source_origins(self.records['sources'])
        self.claims, self.connectors = active(self.records['claims']), active(self.records['graph'])

        def bearing(record: dict) -> tuple[frozenset, frozenset, frozenset]:
            direct, independent, passages = set(), set(), set()
            for eid in record['evidence_ids']:
                item = evidence[eid]
                found = set().union(*(by_source[sid] for sid in item['source_ids']))
                direct |= found
                passages.update(item['source_ids'])
                if item.get('independent'):
                    independent |= found
            return frozenset(direct), frozenset(independent), frozenset(passages)

        self.direct, self.independent, self.passages = {}, {}, {}
        for claim_id, record in self.claims.items():
            self.direct[claim_id], self.independent[claim_id], self.passages[claim_id] = bearing(record)
        # Count duplicate citation footprints, even when a citation reaches several origins.
        self.citation_origins = {claim_id: {by_source[sid] for sid in passages}
                                 for claim_id, passages in self.passages.items()}
        self.degree = Counter(origin for origins in self.direct.values() for origin in origins)
        self.origins = frozenset(self.degree)
        # A proposition is a group of claims the repository has judged equivalent; a lone claim is its own.
        self.root = equivalence_roots(self.records, self.claims)
        self.members = defaultdict(list)
        for claim_id in sorted(self.root):
            self.members[self.root[claim_id]].append(claim_id)
        self.proposition_direct = {root: frozenset().union(*(self.direct[m] for m in members))
                                   for root, members in self.members.items()}
        self.connector_direct, self.connector_own = {}, {}
        for connector_id, record in self.connectors.items():
            direct = bearing(record)[0]
            ends = self.direct.get(record['from'], EMPTY) | self.direct.get(record['to'], EMPTY)
            self.connector_direct[connector_id] = direct
            self.connector_own[connector_id] = direct - ends
        used = {eid for group in (self.claims, self.connectors) for r in group.values() for eid in r['evidence_ids']}
        self.unattached_evidence = frozenset(evidence) - used
        self.unattached_sources = (frozenset(self.records['sources']) -
                                   {sid for eid in used for sid in evidence[eid]['source_ids']})
        self._reach = {}

    def attribution(self, claim_id: str) -> Fraction:
        """Each origin is one unit shared equally by the claims it bears on (Shapley value of coverage)."""
        return sum((Fraction(1, self.degree[origin]) for origin in self.direct[claim_id]), Fraction(0))

    def reach(self, claim_id: str) -> frozenset:
        """Direct origins plus those inherited through joint premise sets."""
        if claim_id not in self._reach:
            seen, pending, found = {claim_id}, [claim_id], set()
            claims, evidence = self.records['claims'], self.records['evidence']
            while pending:
                current = pending.pop()
                found |= self.direct.get(current, EMPTY)
                for eid in claims[current]['evidence_ids']:
                    for premise in evidence[eid].get('premise_claim_ids', []):
                        if premise in claims and premise not in seen:
                            seen.add(premise)
                            pending.append(premise)
            self._reach[claim_id] = frozenset(found)
        return self._reach[claim_id]

    def coverage(self, ids) -> int:
        """Origins a part reaches on its own."""
        return len(set().union(*(self.direct[i] for i in ids))) if ids else 0

    def exclusive(self, ids) -> int:
        """Origins the model would lose if the part were withdrawn."""
        inside = Counter(origin for i in set(ids) for origin in self.direct[i])
        return sum(1 for origin, count in inside.items() if count == self.degree[origin])

    def shared(self, left, right) -> int:
        """Origins two parts have in common: coverage(A) + coverage(B) - coverage(A ∪ B)."""
        left, right = set(left), set(right)
        return self.coverage(left) + self.coverage(right) - self.coverage(left | right)

    def part(self, ids) -> dict:
        ids = sorted(ids)
        return {'claims': len(ids), 'origins_reached': self.coverage(ids),
                'origins_exclusive': self.exclusive(ids),
                'origins_attributed': exact(sum((self.attribution(i) for i in ids), Fraction(0))),
                'links': sum(len(self.direct[i]) for i in ids),
                'citations': sum(len(self.passages[i]) for i in ids)}

    def totals(self) -> dict:
        links, citations = sum(self.degree.values()), sum(map(len, self.passages.values()))
        return {'claims': len(self.claims), 'propositions': len(self.members),
                'proposition_links': sum(map(len, self.proposition_direct.values())),
                'origins': len(self.origins), 'links': links,
                'citations': citations, 'repeat_citations': citations - sum(map(len, self.citation_origins.values())),
                'connectors': len(self.connectors),
                'connectors_with_own_origins': sum(1 for own in self.connector_own.values() if own),
                'unattached_evidence': len(self.unattached_evidence)}


def bucket(count: int) -> str:
    return str(count) if count <= 2 else '3-5' if count <= 5 else '6-10' if count <= 10 else '11+'


def ledger(records: dict) -> dict:
    m = Measure(records)
    totals = m.totals()
    links = totals['links']
    strata = Counter(stratum for stratum, _ in m.origins)
    basis = Counter(key.split(':', 1)[0] for _, key in m.origins)
    square = sum(count * count for count in m.degree.values())
    entropy = -sum((count / links) * math.log2(count / links) for count in m.degree.values()) if links else 0.0
    observational = {i: sum(1 for o in m.direct[i] if o[0] == 'observational') for i in m.claims}
    sole = Counter(next(iter(m.direct[i])) for i in m.claims if len(m.direct[i]) == 1)
    sources = m.records['sources']
    cited = set().union(*m.passages.values()) if m.passages else set()
    folded = {root: members for root, members in m.members.items() if len(members) > 1}

    def stratify(field: str) -> dict:
        groups = defaultdict(list)
        for claim_id, record in m.claims.items():
            groups[record[field]].append(claim_id)
        return {name: m.part(ids) for name, ids in sorted(groups.items())}

    return {
        'ledger_version': LEDGER_VERSION,
        'totals': {
            'claims': totals['claims'], 'propositions': totals['propositions'],
            'origins': totals['origins'],
            'origins_by_stratum': {name: strata.get(name, 0) for name in STRATUM_ORDER},
            'origins_by_identity_basis': {name: basis.get(name, 0) for name in IDENTITY_BASES},
            'links': links, 'citations': totals['citations'],
            'repeat_citations': totals['repeat_citations'],
        },
        'connectors': {
            'connectors': totals['connectors'],
            'with_own_origins': totals['connectors_with_own_origins'],
            'repeating_endpoint_origins_only': totals['connectors'] - totals['connectors_with_own_origins'],
        },
        'equivalence': {
            'groups': len(folded),
            'claims_in_groups': sum(map(len, folded.values())),
            'claims_folded': totals['claims'] - totals['propositions'],
            'groups_drawing_on_several_origins': sum(1 for root, members in folded.items()
                                                     if len(m.proposition_direct[root]) > max(len(m.direct[c]) for c in members)),
            'propositions_with_several_origins': sum(1 for origins in m.proposition_direct.values() if len(origins) > 1),
            'proposition_links': totals['proposition_links'],
            'compared_pairs': dict(sorted(Counter(outcome for pair, outcome in current_comparisons(records).items()
                                                  if pair[0] in m.claims and pair[1] in m.claims).items())),
        },
        'inert': {
            'unattached_evidence': len(m.unattached_evidence),
            'unattached_sources': len(m.unattached_sources),
            'retired_claims': len(m.records['claims']) - len(m.claims),
            'retired_connectors': len(m.records['graph']) - len(m.connectors),
        },
        'concentration': {
            'effective_origins_order2': exact(Fraction(links * links, square) if square else 0),
            'effective_origins_shannon': round(2 ** entropy, 6) if links else 0.0,
            'entropy_bits': round(entropy, 6),
            'largest_origin_share': exact(Fraction(max(m.degree.values()), links) if links else 0),
        },
        'claim_support': {
            'origins_per_claim': dict(sorted(Counter(bucket(len(m.direct[i])) for i in m.claims).items())),
            'observational_origins_per_claim': dict(sorted(Counter(bucket(n) for n in observational.values()).items())),
            'with_reviewed_independent_origin': sum(1 for i in m.claims if m.independent[i]),
            'with_inherited_reach': sum(1 for i in m.claims if m.reach(i) != m.direct[i]),
            'single_origin_claims': sum(1 for i in m.claims if len(m.direct[i]) == 1),
            'origins_that_are_sole_support': len(sole),
            'most_claims_resting_on_one_origin': max(sole.values(), default=0),
        },
        'by_class': stratify('class'),
        'by_uncertainty': stratify('uncertainty'),
        'commitment': Commitment(records).report(),
        'unmeasured': {
            'claims_without_valid_time': sum(1 for r in m.claims.values() if not r.get('valid_time')),
            'claims_without_declared_resolution': len(m.claims),
            'cited_sources_without_ancestry': sum(1 for sid in cited if not sources[sid].get('ancestry')),
            'cited_sources_without_date': sum(1 for sid in cited if not sources[sid].get('date')),
        },
    }


def tokens(text: str) -> frozenset:
    return frozenset(re.findall(r'\w+', text.casefold()))


def restatement_cues(old: Measure, new: Measure, added: list[str]) -> list[dict]:
    """Review cues only: lexical overlap with an earlier claim on a shared origin.

    Never enters a total. A measure that read wording could be raised by wording.
    """
    compared = current_comparisons(new.records)
    by_origin = defaultdict(set)
    for claim_id, origins in old.direct.items():
        for origin in origins:
            by_origin[origin].add(claim_id)
    cache, cues = {}, []

    def bag(m: Measure, claim_id: str) -> frozenset:
        if claim_id not in cache:
            cache[claim_id] = tokens(m.claims[claim_id]['statement'])
        return cache[claim_id]

    for claim_id in added:
        mine, best = bag(new, claim_id), None
        for candidate in sorted(set().union(*(by_origin[o] for o in new.direct[claim_id])) if new.direct[claim_id] else ()):
            if tuple(sorted((claim_id, candidate))) in compared:
                continue  # already judged by review; a cue would add nothing
            theirs = bag(old, candidate)
            union = len(mine | theirs)
            score = Fraction(len(mine & theirs), union) if union else Fraction(0)
            if best is None or score > best[0]:
                best = (score, candidate)
        if best and best[0] >= CUE_THRESHOLD:
            cues.append({'kind': 'possible_restatement', 'basis': 'heuristic', 'claim_id': claim_id,
                         'earlier_claim_id': best[1], 'token_overlap': exact(best[0]),
                         'shared_origins': len(new.direct[claim_id] & old.direct[best[1]])})
    return cues


# --- Commitment: what the claims rule out, per declared question -------------------------------
#
# A question may declare an answer `space`; a claim may declare `answers`, each naming a question
# and the part of its space the claim admits (schema 1.3, see scripts/answers.py). Both are
# optional, so this section measures nothing until a repository declares them.

INFINITE = 'infinite'


def bits(ratio) -> dict:
    """log2 of an exact ratio. The ratio is printed while it stays short; a long one is given in bits alone."""
    ratio = Fraction(ratio)
    short = max(ratio.numerator.bit_length(), ratio.denominator.bit_length()) <= 256
    return {'ratio': f'{ratio.numerator}/{ratio.denominator}' if short else None,
            'bits': round(math.log2(ratio.numerator) - math.log2(ratio.denominator), 6)}


def cells(space: dict, answers: dict) -> list[tuple[Fraction, frozenset]]:
    """Split the space into pieces on which the set of admitting claims is constant."""
    if space['kind'] == 'categorical':
        return [(Fraction(1), frozenset(c for c, admitted in answers.items() if value in admitted))
                for value in sorted(space['values'])]
    points = {0, grid(space)[2]}
    for admitted in answers.values():
        for start, end in admitted:
            points.update((start, end))
    points = sorted(points)
    return [(Fraction(right - left), frozenset(c for c, admitted in answers.items()
                                     if any(start <= left and right <= end for start, end in admitted)))
            for left, right in zip(points, points[1:])]


def question_state(space: dict, answers: dict) -> dict:
    """The model's state on one question.

    An answer stays admitted when no other answer is admitted by a strictly larger
    set of claims. Consistent claims therefore leave their intersection; claims
    that cannot all hold leave the union of what each consistent group allows.
    """
    pieces = cells(space, answers)
    groups = {members for _, members in pieces}
    maximal = {members for members in groups if not any(members < other for other in groups)}
    return {'space': sum((weight for weight, _ in pieces), Fraction(0)),
            'admitted': sum((weight for weight, members in pieces if members in maximal), Fraction(0)),
            'maximal': maximal}


def surprise(space: dict, answers: dict, incoming) -> Fraction | None:
    """Ratio by which an incoming answer cuts the admitted set; None when it cuts it to nothing."""
    key = object()
    before = question_state(space, answers)
    overlap = sum((weight for weight, members in cells(space, {**answers, key: incoming})
                   if key in members and members - {key} in before['maximal']), Fraction(0))
    return Fraction(before['admitted'], overlap) if overlap else None


class Commitment:
    """Declared questions and the answers active claims give them."""

    def __init__(self, records: dict):
        self.records = records
        self.questions = {qid: q for qid, q in records.get('questions', {}).items()
                          if q.get('space') and q.get('state', 'open') != 'retired'}
        self.answers = {qid: {} for qid in self.questions}
        self.written = defaultdict(dict)
        self.claims = active(records.get('claims', {}))
        for claim_id, record in self.claims.items():
            for answer in record.get('answers', []):
                self.written[answer['question_id']][claim_id] = answer
                if answer['question_id'] in self.questions:
                    space = self.questions[answer['question_id']]['space']
                    self.answers[answer['question_id']][claim_id] = admitted_set(space, answer)
        self.states = {qid: question_state(q['space'], self.answers[qid]) for qid, q in self.questions.items()}

    def held(self, qid: str) -> Fraction:
        state = self.states[qid]
        return Fraction(state['space'], state['admitted'])

    def report(self) -> dict:
        rows, total, focus, limit = {}, Fraction(1), Fraction(1), Fraction(1)
        for qid in sorted(self.questions):
            state, ratio = self.states[qid], self.held(qid)
            total *= ratio
            if self.questions[qid].get('focus'):
                focus *= ratio
            limit *= capacity(self.questions[qid]['space'])
            rows[qid] = {'held': bits(ratio), 'capacity': bits(capacity(self.questions[qid]['space'])),
                         'answers': len(self.answers[qid]),
                         'consistent_groups': len(state['maximal']) if self.answers[qid] else 0,
                         'conflict': len(state['maximal']) > 1, 'focus': bool(self.questions[qid].get('focus'))}
        answering = {claim_id for answers in self.answers.values() for claim_id in answers}
        roots, disagreeing = equivalence_roots(self.records, self.claims), set()
        for answers in self.answers.values():
            given = {}
            for claim_id, admitted in sorted(answers.items()):
                if given.setdefault(roots[claim_id], admitted) != admitted:
                    disagreeing.add(roots[claim_id])
        return {'questions': len(rows), 'questions_in_conflict': sum(1 for row in rows.values() if row['conflict']),
                'held': bits(total), 'capacity': bits(limit), 'held_on_focus': bits(focus),
                'questions_fully_resolved': sum(1 for qid in rows if self.states[qid]['admitted'] == 1),
                'claims_answering': len(answering), 'claims_answering_nothing': len(self.claims) - len(answering),
                'equivalent_groups_answering_differently': len(disagreeing),
                'by_question': rows}


def commitment_delta(before: dict, after: dict) -> dict:
    """Per question: bits held before and after, and how each incoming answer met the earlier state.

    Surprise is measured against the earlier state alone. The gain is the difference between
    the two states for the whole step. They coincide when the earlier state is consistent and
    one answer arrives. Cells of two different spaces are never compared with each other.
    """
    old, new = Commitment(before), Commitment(after)
    rows, total, focus, lost = {}, Fraction(1), Fraction(1), Fraction(1)
    verdicts = Counter()
    for qid in sorted(old.questions.keys() | new.questions.keys()):
        asked_before, asked_after = qid in old.questions, qid in new.questions
        prior, current = old.answers.get(qid, {}), new.answers.get(qid, {})
        same_space = asked_before and asked_after and old.questions[qid]['space'] == new.questions[qid]['space']
        if same_space and prior == current:
            continue
        question = new.questions.get(qid) or old.questions[qid]
        held_before = old.held(qid) if asked_before else Fraction(1)
        held_after = new.held(qid) if asked_after else Fraction(1)
        families = new.states[qid]['maximal'] if asked_after else set()
        comparable = same_space or not asked_before  # a new question has no earlier cells to mix with
        answers = {}
        for claim_id in sorted(prior.keys() | current.keys()):
            was, now = prior.get(claim_id), current.get(claim_id)
            if comparable and was == now:
                continue
            # 'claim' when the claim's own answer record changed; 'question' when only its question did.
            row = {'by': 'claim' if old.written.get(qid, {}).get(claim_id) != new.written.get(qid, {}).get(claim_id)
                   else 'question'}
            if now is None:
                verdict = 'withdrawn'
            elif not comparable:
                verdict = 'space_changed'
            elif was is None:
                space = question['space']
                cut = Fraction(1) if now in prior.values() else surprise(space, prior, now)
                row['surprise'] = INFINITE if cut is None else bits(cut)
                contested = len(families) > 1 and any(claim_id not in family for family in families)
                if cut is None:
                    verdict = 'conflicts'
                elif not prior:
                    verdict = 'conflicts' if contested else 'first_answer'
                elif cut == 1:
                    verdict = 'repeats'
                else:
                    verdict = 'conflicts' if contested else 'narrows'
            else:
                space = question['space']
                alone_before = question_state(space, {claim_id: was})['admitted']
                alone_after = question_state(space, {claim_id: now})['admitted']
                both = question_state(space, {0: was, 1: now})
                contained = len(both['maximal']) == 1 and both['admitted'] == min(alone_before, alone_after)
                verdict = ('widened' if contained and alone_after > alone_before else
                           'narrowed' if contained and alone_after < alone_before else 'changed')
                row['own_width'] = bits(Fraction(alone_before, alone_after))
            row['verdict'] = verdict
            answers[claim_id] = row
            verdicts[verdict] += 1
        gain = Fraction(held_after, held_before)
        total *= gain
        if question.get('focus'):
            focus *= gain
        if gain < 1 and same_space:
            lost *= gain
        rows[qid] = {'held_before': bits(held_before), 'held_after': bits(held_after), 'gain': bits(gain),
                     'conflict_before': asked_before and len(old.states[qid]['maximal']) > 1,
                     'conflict_after': asked_after and len(new.states[qid]['maximal']) > 1,
                     'space_changed': asked_before and asked_after and not same_space,
                     'focus': bool(question.get('focus')), 'answers': answers}
    return {'gain': bits(total), 'gain_on_focus': bits(focus), 'gain_off_focus': bits(total / focus), 'loss': bits(lost),
            'verdicts': dict(sorted(verdicts.items())), 'questions': rows}


MEASURED_FIELDS = ('class', 'uncertainty', 'valid_time')
GRADE = {'low': 0, 'medium': 1, 'high': 2}
COLUMNS = ('claims', 'origins', 'links', 'citations')


def delta(before: dict, after: dict) -> dict:
    """Explain every change in the totals by a verdict on one record.

    Each origin that enters or leaves the model is shared equally by the claims
    responsible in this step, so per-claim gains sum exactly to the difference
    of the two ledgers. A step that cannot be explained this way is an error.
    """
    old, new = Measure(before), Measure(after)
    entered, left = new.origins - old.origins, old.origins - new.origins
    introducers, removers, rows = Counter(), Counter(), {}
    for claim_id in sorted(old.claims.keys() | new.claims.keys()):
        was, now = claim_id in old.claims, claim_id in new.claims
        d_old, d_new = old.direct.get(claim_id, EMPTY), new.direct.get(claim_id, EMPTY)
        p_old, p_new = old.passages.get(claim_id, EMPTY), new.passages.get(claim_id, EMPTY)
        gained, lost = d_new - d_old, d_old - d_new
        r_old, r_new = old.claims.get(claim_id, {}), new.claims.get(claim_id, {})
        effects = []
        if now and not was:
            verdict = ('reactivated' if claim_id in before.get('claims', {}) else
                       'new_claim_new_origin' if gained & entered else 'new_claim_known_origins')
        elif was and not now:
            verdict = 'retired' if claim_id in after.get('claims', {}) else 'removed'
        else:
            added_passages = p_new - p_old
            added_citation_origins = added_passages and new.citation_origins[claim_id] - old.citation_origins[claim_id]
            # The same source records resolving to another origin is an identity change, not a change of support.
            verdict = ('origin_reidentified' if (gained or lost) and p_old == p_new else
                       'support_changed' if gained and lost else 'gains_origin' if gained else
                       'support_withdrawn' if lost else 'adds_citation' if added_citation_origins else
                       'repeat_citation' if added_passages else
                       'citations_withdrawn' if p_old - p_new else None)
            changed = [field for field in MEASURED_FIELDS if r_old.get(field) != r_new.get(field)]
            if changed:
                effects.append('reassessed:' + ','.join(changed))
            if r_old.get('statement') != r_new.get('statement'):
                effects.append('text_edited')
            if verdict is None:
                if not effects:
                    continue
                verdict = 'reassessed' if changed else 'unmeasured_edit'
        loss = []
        if was and not now:
            loss.append('retired')
        if was and now and lost and p_old - p_new:
            loss.append('support_withdrawn')
        if was and now and GRADE.get(r_new.get('uncertainty'), 0) > GRADE.get(r_old.get('uncertainty'), 0):
            loss.append('uncertainty_raised')
        for origin in gained & entered:
            introducers[origin] += 1
        for origin in lost & left:
            removers[origin] += 1
        rows[claim_id] = {'verdict': verdict, 'effects': effects, 'loss': loss, 'claims': int(now) - int(was),
                          'links': len(d_new) - len(d_old), 'citations': len(p_new) - len(p_old),
                          'origins_new_to_claim': len(gained), 'origins_new_to_model': len(gained & entered),
                          'origins_lost_by_claim': len(lost), '_gained': gained & entered, '_lost': lost & left}
    gain = {column: Fraction(0) for column in COLUMNS}
    verdicts = Counter()
    for row in rows.values():
        share = (sum((Fraction(1, introducers[o]) for o in row.pop('_gained')), Fraction(0)) -
                 sum((Fraction(1, removers[o]) for o in row.pop('_lost')), Fraction(0)))
        row['origins'] = exact(share)
        gain['origins'] += share
        for column in ('claims', 'links', 'citations'):
            gain[column] += row[column]
        verdicts[row['verdict']] += 1
    before_totals, after_totals = old.totals(), new.totals()
    if any(gain[column] != after_totals[column] - before_totals[column] for column in COLUMNS):
        raise Invalid('Ledger residual: verdicts do not explain the difference between the two states')
    connector_verdicts, connector_rows = Counter(), {}
    for connector_id in sorted(old.connectors.keys() | new.connectors.keys()):
        was, now = connector_id in old.connectors, connector_id in new.connectors
        if now and not was:
            verdict = 'new_connector_own_origins' if new.connector_own[connector_id] else 'new_connector_endpoint_origins'
        elif was and not now:
            verdict = 'connector_retired'
        elif old.connectors[connector_id] != new.connectors[connector_id]:
            verdict = 'connector_edited'
        else:
            continue
        connector_rows[connector_id] = {'verdict': verdict}
        connector_verdicts[verdict] += 1
    added = [claim_id for claim_id, row in rows.items() if row['claims'] == 1]
    step_origins = set().union(*(new.direct[i] for i in rows if i in new.direct)) if rows else set()
    known = len(step_origins & old.origins)
    numbers = {column: int(gain[column]) for column in COLUMNS}
    extra = {key: after_totals[key] - before_totals[key]
             for key in ('repeat_citations', 'propositions', 'proposition_links', 'connectors',
                         'connectors_with_own_origins', 'unattached_evidence')}
    equivalences = []
    for root, members in sorted(new.members.items()):
        if len({old.root.get(claim_id, claim_id) for claim_id in members}) > 1:
            widest = max(len(new.direct[c]) for c in members)
            equivalences.append({'claims': members, 'origins': len(new.proposition_direct[root]),
                                 'verdict': 'adds_origins' if len(new.proposition_direct[root]) > widest else 'same_origins'})
    commitment = commitment_delta(before, after)
    for question in commitment['questions'].values():
        for claim_id, answer in question['answers'].items():
            if answer['verdict'] in ('widened', 'withdrawn') and answer['by'] == 'claim' and claim_id in new.claims:
                row = rows.setdefault(claim_id, {'verdict': 'answer_changed', 'effects': [], 'loss': [], 'claims': 0,
                                                 'links': 0, 'citations': 0, 'origins_new_to_claim': 0,
                                                 'origins_new_to_model': 0, 'origins_lost_by_claim': 0,
                                                 'origins': exact(0)})
                row['loss'].append('answer_' + answer['verdict'])
    folded_now = {claim_id for group in equivalences for claim_id in group['claims']}
    for claim_id, row in rows.items():
        row['at_equivalence'] = claim_id in folded_now
    identity_only = (bool(rows) and all(row['verdict'] == 'origin_reidentified' for row in rows.values())
                     and not connector_rows and not commitment['questions'] and not equivalences)
    if identity_only:
        outcome = 'origin_identity_changed'
    elif numbers['origins'] > 0:
        outcome = 'adds_origins'
    elif numbers['claims'] > 0:
        outcome = 'adds_claims_on_known_origins'
    elif numbers['links'] > 0:
        outcome = 'adds_links'
    elif min(numbers.values()) < 0 or extra['connectors'] < 0:
        outcome = 'loss'
    elif extra['connectors'] > 0:
        outcome = 'adds_connectors'
    elif commitment['questions']:
        outcome = 'changes_commitment'
    elif numbers['citations'] > 0:
        outcome = 'adds_citations' if verdicts.get('adds_citation') else 'repeat_citations_only'
    elif equivalences:
        outcome = 'records_equivalence'
    elif verdicts.get('origin_reidentified'):
        outcome = 'origin_identity_changed'
    elif verdicts.get('reassessed'):
        outcome = 'reassessment_only'
    elif rows or connector_rows:
        outcome = 'unmeasured_edit_only'
    elif extra['unattached_evidence']:
        outcome = 'unattached_material_only'
    else:
        outcome = 'no_change'
    return {
        'ledger_version': LEDGER_VERSION, 'outcome': outcome,
        'gain': {**numbers, **extra},
        'origins_entered': len(entered), 'origins_left': len(left),
        'origins_entered_by_stratum': {name: sum(1 for stratum, _ in entered if stratum == name)
                                       for name in STRATUM_ORDER},
        'step_origins': len(step_origins), 'step_origins_already_known': known,
        'known_origin_share': exact(Fraction(known, len(step_origins))) if step_origins else None,
        'verdicts': dict(sorted((verdicts + connector_verdicts).items())),
        'claims': rows, 'connectors': connector_rows, 'equivalences': equivalences,
        'commitment': commitment,
        'review_cues': restatement_cues(old, new, added),
    }


# --- Currency: how admitted information has held up, measured from the repository's own history ----
#
# Nothing here assigns a lifetime to a claim. What can be known is how old each claim's
# admission, last review and newest evidence are, and how often this repository's reviews
# have found that an admitted claim had to be weakened or withdrawn. Rates are stated with
# intervals from the counts, applied to groups of claims only, and re-tested on every replay.

DAY = 86400
Z95 = 1.959964


def wilson(events: int, trials: int) -> list | None:
    """95% score interval for a proportion, from the two counts alone; None when they are not a proportion."""
    if not trials or not 0 <= events <= trials:
        return None
    share, z2 = events / trials, Z95 * Z95
    centre, spread = share + z2 / (2 * trials), Z95 * math.sqrt(share * (1 - share) / trials + z2 / (4 * trials * trials))
    return [round(max(0.0, (centre - spread) / (1 + z2 / trials)), 6), round(min(1.0, (centre + spread) / (1 + z2 / trials)), 6)]


def byar(events: int) -> tuple[float, float]:
    """95% bounds on a Poisson mean given an observed count (Byar's approximation)."""
    low = events * (1 - 1 / (9 * events) - Z95 / (3 * math.sqrt(events))) ** 3 if events else 0.0
    high = (events + 1) * (1 - 1 / (9 * (events + 1)) + Z95 / (3 * math.sqrt(events + 1))) ** 3
    return max(0.0, low), high


def poisson_quantile(mean: float, level: float) -> int:
    """Smallest count whose cumulative probability reaches the level."""
    if mean > 500:
        # exp(-mean) underflows long before this matters; the normal form is accurate here.
        return max(0, math.floor(mean + statistics.NormalDist().inv_cdf(level) * math.sqrt(mean) + 0.5))
    term = total = math.exp(-mean)
    count = 0
    while total < level and count < 100000:
        count += 1
        term *= mean / count
        total += term
    return count


def period_end(text) -> int | None:
    """Last day a reported source date can mean, as a day number; None when it is not a plain date."""
    match = re.fullmatch(r'(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?', str(text or ''))
    if not match:
        return None
    year, month, day = (int(part) if part else None for part in match.groups())
    if year < 1 or (month is not None and not 1 <= month <= 12) or (day is not None and day < 1):
        return None
    try:
        if day:
            return date(year, month, day).toordinal()
        if month:
            return (date(year + (month == 12), month % 12 + 1, 1)).toordinal() - 1
        return date(year, 12, 31).toordinal()
    except ValueError:
        return None


def spread(values: list) -> dict | None:
    """Nearest-rank summary; no interpolation, so it is exact for the values given."""
    if not values:
        return None
    ordered = sorted(values)
    pick = lambda share: ordered[min(len(ordered) - 1, max(0, math.ceil(share * len(ordered)) - 1))]
    return {'count': len(ordered), 'min': round(ordered[0], 4), 'quartile1': round(pick(0.25), 4),
            'median': round(pick(0.5), 4), 'quartile3': round(pick(0.75), 4), 'max': round(ordered[-1], 4)}


def rate_report(events: int, exposure: float) -> dict:
    low, high = byar(events)
    report = {'events': events, 'exposure': round(exposure, 4),
              'estimate': round(events / exposure, 8) if exposure else None,
              'interval95': [round(low / exposure, 8), round(high / exposure, 8)] if exposure else None}
    return report


def currency(timeline: list[dict], final: Measure, admitted: dict, reviewed: dict, window_days: int = 1) -> dict:
    """Clocks, observed attrition, a bounded projection and a walk-forward test of that projection.

    `timeline` holds, per revision in order: time, active claims, cumulative claim-seconds,
    review instances and the loss events found at that revision.
    """
    if not timeline or not final.claims:
        return {'measured': False, 'reason': 'no admitted claims in this history'}
    as_of, start = timeline[-1]['time'], next(row['time'] for row in timeline if row['active'])
    span = (as_of - start) / DAY
    sources, evidence = final.records['sources'], final.records['evidence']
    today = datetime.fromtimestamp(as_of, timezone.utc).date().toordinal()
    evidence_age, undated = [], 0
    for claim_id, record in final.claims.items():
        ends = [period_end(sources[sid].get('date')) for eid in record['evidence_ids'] for sid in evidence[eid]['source_ids']]
        ends = [end for end in ends if end is not None]
        if ends:
            evidence_age.append(max(0, today - max(ends)))  # a source dated only by year may be newer than as_of
        else:
            undated += 1
    losses = [event for row in timeline for event in row['losses']]
    reviews = timeline[-1]['reviews']
    exposure = timeline[-1]['claim_seconds'] / DAY
    by_kind = Counter(kind for event in losses for kind in event['kinds'])
    per_day = rate_report(len(losses), exposure)
    folded = sum(1 for event in losses if event['at_equivalence'])
    at_review = sum(1 for event in losses if event['at_review'])
    horizon = min(7.0, span)
    low, high = byar(len(losses))
    expected = lambda rate: round(rate * len(final.claims) * horizon, 4)
    keeping = lambda rate: round(math.exp(-rate * horizon), 6)
    # Walk-forward: at each window start use only earlier history, then compare with what happened.
    rows, covered = [], 0
    index, boundary = 0, start + window_days * DAY
    while boundary + window_days * DAY <= as_of:
        while index + 1 < len(timeline) and timeline[index + 1]['time'] <= boundary:
            index += 1
        row = timeline[index]
        seen = sum(len(item['losses']) for item in timeline[:index + 1])
        base = (row['claim_seconds'] + row['active'] * (boundary - row['time'])) / DAY
        realised = sum(len(item['losses']) for item in timeline if boundary < item['time'] <= boundary + window_days * DAY)
        if base > 0:
            floor, ceiling = byar(seen)
            ahead = row['active'] * window_days
            predicted = [poisson_quantile(floor / base * ahead, 0.025), poisson_quantile(ceiling / base * ahead, 0.975)]
            inside = predicted[0] <= realised <= predicted[1]
            covered += inside
            rows.append({'window_start_days': round((boundary - start) / DAY, 4), 'earlier_losses': seen,
                         'earlier_claim_days': round(base, 2), 'predicted': predicted, 'realised': realised, 'inside': inside})
        boundary += window_days * DAY
    never = [claim_id for claim_id in final.claims if claim_id not in reviewed]
    return {
        'measured': True,
        'as_of': datetime.fromtimestamp(as_of, timezone.utc).isoformat().replace('+00:00', 'Z'),
        'history_days': round(span, 4),
        'clocks_days': {
            'since_admitted': spread([(as_of - admitted[c]) / DAY for c in final.claims]),
            'since_last_review': spread([(as_of - reviewed[c]) / DAY for c in final.claims if c in reviewed]),
            'never_reviewed': len(never),
            'since_newest_evidence_reported_at_least': spread(evidence_age),
            'no_dated_evidence': undated,
        },
        'attrition': {
            'reviews': reviews, 'losses': len(losses), 'losses_by_kind': dict(sorted(by_kind.items())),
            'losses_when_folded_as_equivalent': folded, 'losses_otherwise': len(losses) - folded,
            # Only a loss found in the step that reviewed the claim is a share of reviews.
            'losses_found_at_review': at_review, 'losses_outside_review': len(losses) - at_review,
            'loss_per_review': {'estimate': round(at_review / reviews, 6) if reviews else None,
                                'interval95': wilson(at_review, reviews)},
            'loss_per_claim_day': per_day,
            'loss_per_claim_day_otherwise': rate_report(len(losses) - folded, exposure),
            'commitment_bits_lost': round(sum(row['bits_lost'] for row in timeline), 6),
        },
        'projection': {
            'horizon_days': round(horizon, 4), 'claims': len(final.claims),
            'expected_losses': {'estimate': expected(len(losses) / exposure) if exposure else None,
                                'interval95': [expected(low / exposure), expected(high / exposure)] if exposure else None},
            'share_keeping_standing': {'estimate': keeping(len(losses) / exposure) if exposure else None,
                                       'interval95': [keeping(high / exposure), keeping(low / exposure)] if exposure else None},
            'limit': 'A horizon longer than the recorded history is not supported, and no figure applies to a single claim.',
        },
        'walk_forward': {'window_days': window_days, 'windows': len(rows), 'inside': covered, 'rows': rows},
        'unseen': {'claim_days_since_last_review': round(sum((as_of - reviewed.get(c, admitted[c])) / DAY
                                                             for c in final.claims), 2),
                   'note': 'Loss is only found when a claim is reviewed; this is the exposure no review has covered.'},
    }


class History:
    """Read canonical records at Git revisions; unchanged blobs are parsed once."""

    def __init__(self, repo: Path):
        self.repo, self.cache = Path(repo), {}

    def git(self, *args: str, input: bytes | None = None) -> bytes:
        done = subprocess.run(['git', '--no-replace-objects', '-C', str(self.repo), *args],
                              input=input, capture_output=True)
        if done.returncode:
            raise Invalid('Git operation failed: ' + args[0])
        return done.stdout

    def commit(self, revision: str) -> str:
        """Resolve a revision to a commit ID; the name itself never reaches another Git command."""
        if not isinstance(revision, str) or not revision or revision.startswith('-'):
            raise Invalid('Not a revision')
        found = self.git('rev-parse', '--verify', '--quiet', '--end-of-options', revision + '^{commit}').decode().strip()
        if not re.fullmatch(r'[0-9a-f]{40,64}', found):
            raise Invalid('Not a revision')
        return found

    def revisions(self, revision: str) -> list[tuple[str, int, str]]:
        """First-parent history, oldest first: the same line knowledge time selects on."""
        fields = self.git('log', '--first-parent', '--reverse', '-z', '--format=%H%x00%ct%x00%s',
                          self.commit(revision)).decode('utf-8', 'replace').split('\0')
        if fields and fields[-1] == '':
            fields.pop()
        # NUL-separated: a subject may hold any other character, including line separators.
        if len(fields) % 3:
            raise Invalid('Unexpected history listing')
        return [(fields[i], int(fields[i + 1]), fields[i + 2]) for i in range(0, len(fields), 3)]

    def records(self, revision: str) -> dict:
        """Records at a revision, read as the compiler reads them.

        Only regular files at a record's fixed path count, parsed by the compiler's own
        strict loader, with the ID matching the file name. A submodule entry has no file in
        a checkout, so the compiler never sees it and neither does this.
        """
        entries = []
        listing = self.git('ls-tree', '-r', '-z', '--full-tree', self.commit(revision), '--', *GROUPS, *JUDGMENT_ROOTS)
        for entry in listing.split(b'\0'):
            if not entry:
                continue
            meta, raw = entry.split(b'\t', 1)
            if not RECORD_PATH.fullmatch(raw):
                continue
            mode, kind, oid = meta.decode('ascii').split()
            if kind == 'commit':
                continue
            if kind != 'blob' or mode not in ('100644', '100755'):
                raise Invalid('Data records must be regular files')
            try:
                entries.append((raw.decode('utf-8'), oid))
            except UnicodeDecodeError as exc:
                raise Invalid('Record paths must be UTF-8') from exc
        missing = sorted({oid for _, oid in entries if oid not in self.cache})
        if missing:
            out = self.git('cat-file', '--batch', input=('\n'.join(missing) + '\n').encode())
            offset = 0
            for oid in missing:
                end = out.find(b'\n', offset)
                header = out[offset:end].split() if end >= 0 else []
                if len(header) != 3 or header[1] != b'blob' or int(header[2]) > MAX_FILE_BYTES:
                    raise Invalid('Missing, oversized or unexpected record object')
                size = int(header[2])
                try:
                    record = yaml.load(out[end + 1:end + 1 + size].decode('utf-8'), Loader=StrictLoader)
                except (yaml.YAMLError, UnicodeError) as exc:
                    raise Invalid('Cannot parse a record') from exc
                if not isinstance(record, dict) or not isinstance(record.get('id'), str):
                    raise Invalid('A record must be an object with an ID')
                self.cache[oid] = record
                offset = end + 1 + size + 1
        records = {group: {} for group in GROUPS}
        judgments = []
        for path, oid in entries:
            record = self.cache[oid]
            if record['id'] != path.rsplit('/', 1)[1][:-len('.yaml')]:
                raise Invalid('Record ID does not match its file name')
            if path.startswith(JUDGMENT_ROOTS):
                judgments.append(record)
            else:
                records[path.split('/', 1)[0]][record['id']] = record
        records['operations'] = collect_operations(judgments)
        records['reviews'] = collect_reviews(judgments)
        return records

    def replay(self, revision: str, deadline: float | None = None) -> dict:
        steps, previous = [], {group: {} for group in GROUPS}
        running = Counter()
        timeline, admitted, reviewed, counted = [], {}, {}, set()
        seconds, reviews, last, active_before = 0, 0, None, 0
        for commit, committed, subject in self.revisions(revision):
            if deadline is not None and time.monotonic() > deadline:
                raise Invalid('history is longer than the time allowed for replay')
            # A committer time earlier than its parent's is read as its parent's, so no span is negative.
            recorded = committed if last is None else max(last, committed)
            current = self.records(commit)
            step = delta(previous, current)
            state = ledger(current)
            if last is not None:
                seconds += active_before * max(0, recorded - last)
            for claim_id in current['claims']:
                admitted.setdefault(claim_id, recorded)
            fresh = set()
            for review_id, claim_ids in sorted(current.get('reviews', {}).items()):
                if review_id not in counted:
                    counted.add(review_id)
                    reviews += len(claim_ids)
                    fresh.update(claim_ids)
                    for claim_id in claim_ids:
                        reviewed[claim_id] = recorded
            losses = [{'claim_id': claim_id, 'kinds': row['loss'], 'at_equivalence': row['at_equivalence'],
                       'at_review': claim_id in fresh}
                      for claim_id, row in step['claims'].items() if row['loss']]
            last, active_before = recorded, len(active(current['claims']))
            timeline.append({'time': recorded, 'active': active_before, 'claim_seconds': seconds, 'reviews': reviews,
                             'losses': losses, 'bits_lost': -step['commitment']['loss']['bits']})
            cues = len(step.pop('review_cues'))
            del step['claims'], step['connectors']
            step['equivalences'] = dict(sorted(Counter(row['verdict'] for row in step['equivalences']).items()))
            step['commitment'] = {key: step['commitment'][key] for key in ('gain', 'gain_on_focus', 'loss', 'verdicts')}
            step['losses'] = len(losses)
            running.update(step['gain'])
            steps.append({'revision': commit, 'committer_time': committed, 'subject': subject,
                          'step': {**step, 'review_cues': cues}, 'totals': state['totals'],
                          'connectors': state['connectors'], 'concentration': state['concentration']})
            previous = current
        final = Measure(previous).totals()
        # Chain rule: the gains of every step, added up, are the final state.
        if any(running[key] != final[key] for key in final):
            raise Invalid('Replay residual: step gains do not sum to the final state')
        return {'ledger_version': LEDGER_VERSION, 'revision': steps[-1]['revision'] if steps else None,
                'outcomes': dict(sorted(Counter(row['step']['outcome'] for row in steps).items())),
                'currency': currency(timeline, Measure(previous), admitted, reviewed),
                'steps': steps}


def percent(value) -> str:
    return 'n/a' if value is None else f'{100 * value:.2f}%'


def summary_head(now: dict, change: dict | None) -> str:
    """A short advisory reading for a job summary. Structure only; it never states that anything is true."""
    totals, lines = now['totals'], ['### Information ledger (advisory)', '']
    lines += ['| | Claims | Propositions | Origins | Links |', '|---|---|---|---|---|',
              f"| Now | {totals['claims']} | {totals['propositions']} | {totals['origins']} | {totals['links']} |"]
    if change:
        gain = change['gain']
        lines.append(f"| This change | {gain['claims']:+d} | {gain['propositions']:+d} | {gain['origins']:+d} | {gain['links']:+d} |")
        lines += ['', f"Outcome: `{change['outcome']}`."]
        share = change['known_origin_share']
        if share is not None:
            lines.append(f"{change['step_origins_already_known']} of the {change['step_origins']} origins this change draws on "
                         f"were already held ({percent(share['approx'])}).")
        if change['review_cues']:
            lines.append(f"{len(change['review_cues'])} new claim(s) resemble an earlier claim on a shared origin and "
                         'have not been compared yet.')
        if change['equivalences']:
            lines.append(f"{len(change['equivalences'])} group(s) of claims newly recorded as equivalent.")
    held = now['commitment']
    if held['questions']:
        moved = f"; this change {change['commitment']['gain']['bits']:+.2f} bits" if change else ''
        lines += ['', f"Commitment: {held['held']['bits']:.2f} of {held['capacity']['bits']:.2f} bits held on "
                      f"{held['questions']} declared question(s), {held['questions_in_conflict']} in conflict{moved}."]
    else:
        lines += ['', 'Commitment: no question declares an answer space, so nothing is measured.']
    return '\n'.join(lines) + '\n'


def summary_history(replayed: dict | None, reason: str | None) -> str:
    found = (replayed or {}).get('currency') or {}
    lines = ['']
    if found.get('measured'):
        seen, test = found['attrition'], found['walk_forward']
        interval = seen['loss_per_review']['interval95']
        lines.append(f"Currency as of {found['as_of']} over {found['history_days']:.1f} days of history: "
                     f"{seen['losses']} loss(es) of standing, {seen['losses_found_at_review']} found in "
                     f"{seen['reviews']} claim reviews"
                     + (f" ({percent(seen['loss_per_review']['estimate'])}, 95% interval "
                        f"{percent(interval[0])} to {percent(interval[1])})" if interval else '')
                     + f"; {seen['losses_when_folded_as_equivalent']} when claims were folded as equivalent. "
                     f"{found['clocks_days']['never_reviewed']} claim(s) never reviewed. "
                     f"Walk-forward check: {test['inside']} of {test['windows']} windows inside the predicted range.")
    else:
        lines.append('Currency: not reported for this change' + (f' ({reason}).' if reason else '.'))
    lines += ['', '_Arithmetic over record structure. It does not measure truth. See `docs/INFORMATION.md`._', '']
    return '\n'.join(lines)


def ci_report(history: 'History', before: str, after: str, out: Path | None, with_history: bool,
              budget: float, write) -> None:
    """Write the reading part by part and flush each, so a slow or failing part never hides the others."""
    def save(name: str, report: dict | None) -> None:
        if out is not None and report is not None:
            try:
                out.mkdir(parents=True, exist_ok=True)
                (out / f'{name}.json').write_bytes(json_bytes(report))
            except OSError:
                pass

    deadline = time.monotonic() + budget
    current = history.records(after)
    now, change = ledger(current), None
    if re.fullmatch(r'[0-9a-f]{7,64}', before or '') and set(before) != {'0'}:
        try:
            change = delta(history.records(before), current)
        except (ValueError, LookupError, TypeError):
            change = None  # an unknown or unreadable base leaves the change unmeasured, never guessed
    save('ledger', now)
    save('change', change)
    write(summary_head(now, change))
    replayed, reason = None, 'history replay was not requested'
    if with_history:
        try:
            replayed = history.replay(after, deadline)
            save('history', replayed)
        except (ValueError, LookupError, TypeError, OverflowError) as exc:
            reason = str(exc) if isinstance(exc, Invalid) else type(exc).__name__
    write(summary_history(replayed, reason))


def working_tree(root: Path) -> dict:
    """Records in a checkout, through the compiler's own reader."""
    def load(folder: str) -> list[dict]:
        found = []
        for path in sorted((Path(root) / folder).glob('*.yaml')):
            record = read_data(path)
            if record.get('id') != path.stem:
                raise Invalid('Record ID does not match its file name')
            found.append(record)
        return found
    records = {group: {record['id']: record for record in load(group)} for group in GROUPS}
    judgments = [record for folder in JUDGMENT_ROOTS for record in load(folder)]
    records['operations'] = collect_operations(judgments)
    records['reviews'] = collect_reviews(judgments)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    commands = parser.add_subparsers(dest='command', required=True)
    one = commands.add_parser('ledger', help='Measure one revision (default: working tree)')
    one.add_argument('--revision')
    two = commands.add_parser('delta', help='Explain the change between two revisions')
    two.add_argument('--before', required=True)
    two.add_argument('--after', required=True)
    many = commands.add_parser('replay', help='Measure every first-parent revision in order')
    many.add_argument('--revision', default='HEAD')
    auto = commands.add_parser('ci', help='Advisory Markdown summary for automation; always exits 0')
    auto.add_argument('--before', default='')
    auto.add_argument('--after', default='HEAD')
    auto.add_argument('--out', type=Path)
    auto.add_argument('--no-history', action='store_true')
    auto.add_argument('--budget', type=float, default=150.0, help='Seconds allowed for the whole report')
    args = parser.parse_args()
    if args.command == 'ci':
        # Advisory by contract: a failure here must never fail the job that called it.
        def write(text: str) -> None:
            try:
                sys.stdout.write(text)
                sys.stdout.flush()
            except OSError:
                # The reader went away. Nothing more can be said, and that is still not a failure.
                sys.stdout = open(os.devnull, 'w', encoding='utf-8')
        try:
            ci_report(History(args.repo), args.before, args.after, args.out, not args.no_history, args.budget, write)
        except Exception as exc:  # noqa: BLE001
            write(f'### Information ledger (advisory)\n\nNot available for this change: {type(exc).__name__}.\n')
        return 0
    try:
        history = History(args.repo)
        if args.command == 'ledger':
            report = ledger(history.records(args.revision) if args.revision else working_tree(args.repo))
        elif args.command == 'delta':
            report = delta(history.records(args.before), history.records(args.after))
        else:
            report = history.replay(args.revision)
    except (OSError, ValueError, TypeError, LookupError, OverflowError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    sys.stdout.buffer.write(json_bytes(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
