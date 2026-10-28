"""Synthetic valid-time, recorded knowledge-time and compatibility regressions."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.build_knowledge import ROOT, compile_revision, knowledge_revision
from scripts.model import Invalid, validate_state
from scripts.query_knowledge import Knowledge
from scripts.temporal import applicability, boundary, point, validate_temporal
from scripts.world_control import canonical_id, plan_admission
from test_model import admitted, contribution, decisions, state_for, write_state


def bound(value, precision='day'):
    return None if value is None else {'precision': precision, 'value': value}


def valid(start='2026-01-01', end='2026-02-01', *, precision='day', start_inclusive=True, end_inclusive=False):
    return {'status': 'specified', 'intervals': [{
        'start': bound(start, precision), 'end': bound(end, precision),
        'start_inclusive': start_inclusive, 'end_inclusive': end_inclusive, 'evidence_ids': ['e1'],
    }], 'notes': ['Synthetic evidence-backed evaluation window.']}


def proposal(token='1' * 32, value=None):
    result = contribution(token=token)
    result['schema_version'] = '1.1'
    result['created_at'] = '2026-04-01T10:00:00Z'
    result['sources'][0]['date'] = '2026-03-01'
    result['claims'][0]['statement'] = 'The synthetic fixture value is 7 during January 2026.'
    result['claims'][0]['valid_time'] = copy.deepcopy(value if value is not None else valid())
    return result


class TemporalTests(unittest.TestCase):
    def status(self, value, at):
        validate_temporal(value, ['e1'])
        return applicability(value, point(at))[0]

    def test_explicit_bound_inclusivity(self):
        self.assertEqual(self.status(valid(), '2026-01-01'), 'matches')
        self.assertEqual(self.status(valid(), '2026-02-01'), 'outside')
        self.assertEqual(self.status(valid(start_inclusive=False), '2026-01-01'), 'outside')
        self.assertEqual(self.status(valid(end_inclusive=True), '2026-02-01'), 'matches')

    def test_open_adjacent_day_bounds_cannot_admit_an_empty_calendar_scope(self):
        empty = valid('2026-01-01', '2026-01-02', start_inclusive=False, end_inclusive=False)
        with self.assertRaisesRegex(ValueError, 'no possible calendar day'):
            validate_temporal(empty, ['e1'])
        with self.assertRaisesRegex(Invalid, 'no possible calendar day'):
            admitted(proposal(value=empty))
        self.assertEqual(self.status(valid('2026-01-01', '2026-01-02'), '2026-01-01'), 'matches')
        self.assertEqual(self.status(valid('2026-01-01', '2026-01-02', start_inclusive=False,
                                          end_inclusive=True), '2026-01-02'), 'matches')

    def test_open_intervals_are_explicit_and_not_unknown_dates(self):
        self.assertEqual(self.status(valid(start=None), '0001-01-01'), 'matches')
        self.assertEqual(self.status(valid(end=None), '9999-12-31'), 'matches')
        self.assertEqual(self.status(valid(start=None, end=None), '2026-01-01T00:00:00Z'), 'matches')
        self.assertEqual(applicability(None, point('2026-01-01')), ('unresolved', 'not_recorded'))

    def test_unknown_and_disputed_annotations_remain_unresolved(self):
        unknown = {'status': 'unknown', 'intervals': [], 'notes': ['No date evidence.']}
        self.assertEqual(self.status(unknown, '2026-01-01'), 'unresolved')
        disputed = valid()
        disputed.update(status='disputed', intervals=disputed['intervals'] + valid('2026-03-01', '2026-04-01')['intervals'])
        self.assertEqual(self.status(disputed, '2026-01-15'), 'unresolved')
        self.assertEqual(self.status(disputed, '2025-01-15'), 'unresolved')

    def test_partial_year_and_month_boundaries_are_not_guessed(self):
        year = valid('2026', '2028', precision='year')
        self.assertEqual(self.status(year, '2026-06-01'), 'unresolved')
        self.assertEqual(self.status(year, '2027-06-01'), 'matches')
        self.assertEqual(self.status(year, '2029-01-01'), 'outside')
        month = valid('2026-01', '2026-04', precision='month')
        self.assertEqual(self.status(month, '2026-01-15'), 'unresolved')
        self.assertEqual(self.status(month, '2026-02-01'), 'matches')

    def test_calendar_leap_days_and_invalid_dates(self):
        self.assertEqual(boundary(bound('2024-02-29'))[0], 'calendar')
        for value in (bound('2026-02-29'), bound('2026-13', 'month'), bound('0000', 'year')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                boundary(value)

    def test_offset_equivalence_preserves_original_clock_representation(self):
        value = valid('2026-01-01T10:00:00+02:00', '2026-01-01T09:00:00Z', precision='instant')
        self.assertEqual(self.status(value, '2026-01-01T08:30:00Z'), 'matches')
        self.assertEqual(self.status(value, '2026-01-01T10:30:00+02:00'), 'matches')
        self.assertEqual(value['intervals'][0]['start']['value'], '2026-01-01T10:00:00+02:00')
        self.assertEqual(self.status(value, '2026-01-01'), 'unresolved')

    def test_rfc_unknown_local_offset_does_not_mean_unknown_utc_instant(self):
        value = valid('2026-01-01T08:00:00-00:00', '2026-01-01T09:00:00Z', precision='instant')
        self.assertEqual(self.status(value, '2026-01-01T08:30:00Z'), 'matches')
        self.assertTrue(value['intervals'][0]['start']['value'].endswith('-00:00'))

    def test_unsupported_precision_and_unqualified_local_times_fail_explicitly(self):
        for value in ('2026-01-01T12:00:00', '2026-01-01T12:00:00.1234567Z', '2026-12-31T23:59:60Z', '2026'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                point(value)

    def test_invalid_order_mixed_clocks_and_duplicate_scopes_fail(self):
        values = [valid('2026-02-01', '2026-01-01'), valid('2026-01-01', '2026-01-01')]
        mixed = valid()
        mixed['intervals'][0]['end'] = bound('2026-02-01T00:00:00Z', 'instant')
        values.append(mixed)
        duplicate = valid()
        duplicate['intervals'].append(copy.deepcopy(duplicate['intervals'][0]))
        values.append(duplicate)
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_temporal(value, ['e1'])

    def test_overlapping_specified_intervals_are_union_not_a_silent_conflict_verdict(self):
        value = valid()
        value['intervals'] += valid('2026-01-15', '2026-03-01')['intervals']
        self.assertEqual(self.status(value, '2026-02-15'), 'matches')
        self.assertEqual(value['status'], 'specified')

    def test_schema_1_0_remains_usable_but_cannot_carry_temporal_extensions(self):
        validate_state(admitted(contribution()), ROOT, True)
        value = proposal()
        value['schema_version'] = '1.0'
        with self.assertRaises(Invalid):
            admitted(value)

    def test_admission_maps_temporal_evidence_without_changing_source_date(self):
        state = admitted(proposal())
        claim = next(record for path, record in state.items() if path.startswith('claims/'))
        self.assertEqual(claim['valid_time']['intervals'][0]['evidence_ids'], claim['evidence_ids'])
        self.assertEqual(claim['valid_time']['intervals'][0]['evidence_ids'], [canonical_id('RUN-' + '1' * 32, 'evidence', 'e1')])
        source = next(record for path, record in state.items() if path.startswith('sources/'))
        self.assertEqual(source['date'], '2026-03-01')
        self.assertEqual(claim['uncertainty'], 'high')

    def test_temporal_evidence_must_belong_to_that_claim(self):
        value = proposal()
        value['claims'][0]['valid_time']['intervals'][0]['evidence_ids'] = ['missing']
        with self.assertRaisesRegex(Invalid, 'Temporal evidence'):
            admitted(value)

    def test_duplicate_same_scope_adds_evidence_without_confidence_promotion(self):
        state = admitted(proposal())
        incoming = proposal('2' * 32)
        incoming['claims'][0]['valid_time']['notes'].append('Another synthetic limitation.')
        state.update(state_for(incoming))
        state.update(plan_admission(state, incoming['id'], decisions(incoming), ROOT))
        self.assertEqual(validate_state(state, ROOT, True)['claims'], 1)
        claim = next(record for path, record in state.items() if path.startswith('claims/'))
        self.assertEqual(len(claim['valid_time']['intervals'][0]['evidence_ids']), 2)
        self.assertEqual(claim['uncertainty'], 'high')
        self.assertIn('Another synthetic limitation.', claim['valid_time']['notes'])

    def test_changed_temporal_scope_is_not_an_implicit_id_rewrite(self):
        state = admitted(proposal())
        incoming = proposal('2' * 32, valid(end='2026-03-01'))
        state.update(state_for(incoming))
        decision = decisions(incoming, 'merge')
        decision['claims']['c1']['target'] = canonical_id('RUN-' + '1' * 32, 'claims', 'c1')
        with self.assertRaisesRegex(Invalid, 'temporal scope differs'):
            plan_admission(state, incoming['id'], decision, ROOT)
        state.update(plan_admission(state, incoming['id'], decisions(incoming), ROOT))
        self.assertEqual(validate_state(state, ROOT, True)['claims'], 2)
        self.assertTrue(all(record['state'] == 'active' for path, record in state.items() if path.startswith('claims/')))

    def test_explicit_unknown_metadata_does_not_duplicate_a_legacy_claim(self):
        state = admitted(contribution())
        incoming = contribution(token='2' * 32)
        incoming['schema_version'] = '1.1'
        incoming['claims'][0]['valid_time'] = {'status': 'unknown', 'intervals': [], 'notes': ['No temporal evidence.']}
        state.update(state_for(incoming))
        state.update(plan_admission(state, incoming['id'], decisions(incoming), ROOT))
        self.assertEqual(validate_state(state, ROOT, True)['claims'], 1)

    def test_missing_temporal_scope_preserves_separate_claim_and_existing_support(self):
        state = admitted(proposal())
        incoming = proposal('2' * 32)
        incoming['schema_version'] = '1.0'
        incoming['claims'][0].pop('valid_time')
        state.update(state_for(incoming))
        state.update(plan_admission(state, incoming['id'], decisions(incoming), ROOT))
        self.assertEqual(validate_state(state, ROOT, True)['claims'], 2)
        claim = next(record for path, record in state.items() if path.startswith('claims/') and 'valid_time' in record)
        self.assertEqual(len(claim['evidence_ids']), 1)
        self.assertEqual(len(claim['valid_time']['intervals'][0]['evidence_ids']), 1)

    def test_local_temporal_definitions_and_bundled_schema_are_synchronized(self):
        claims = json.loads((ROOT / 'docs/schemas/claims.schema.json').read_bytes())
        submission = json.loads((ROOT / 'docs/schemas/submission.schema.json').read_bytes())
        for name in ('time_bound', 'time_interval', 'valid_time'):
            self.assertEqual(claims['$defs'][name], submission['$defs'][name])
        self.assertEqual((ROOT / 'docs/schemas/submission.schema.json').read_bytes(),
                         (ROOT / 'skills/resolvent/references/submission.schema.json').read_bytes())


class TemporalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', '--initial-branch=main', str(self.repo)], check=True)
        (self.repo / 'README.md').write_text('Synthetic history fixture.\n')
        self.before = self.commit({}, '2026-02-01T12:00:00Z')
        self.state = admitted(proposal())
        closure = next(record for path, record in self.state.items() if path.startswith('briefs/closed/'))
        closure['completed_at'] = '2026-04-02T12:00:00Z'
        self.after = self.commit(self.state, '2026-04-02T12:00:00Z')

    def commit(self, state, recorded_at):
        write_state(self.repo, state)
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Synthetic test',
                        '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Synthetic history'],
                       env={**os.environ, 'GIT_AUTHOR_DATE': recorded_at, 'GIT_COMMITTER_DATE': recorded_at}, check=True)
        return subprocess.check_output(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], text=True).strip()

    def reader(self, package, name):
        folder = Path(self.temporary.name) / name
        folder.mkdir()
        for filename, contents in package.items():
            (folder / filename).write_bytes(contents)
        return Knowledge(folder), folder

    def test_historical_admission_and_current_world_valid_time_are_distinct(self):
        old = compile_revision(self.repo, self.after, known_at='2026-02-15T00:00:00Z')
        new = compile_revision(self.repo, self.after)
        historical, _ = self.reader(old, 'historical')
        current, _ = self.reader(new, 'current')
        self.assertEqual(historical.build['source_revision'], self.before)
        self.assertEqual(historical.search()['total'], 0)
        result = current.valid_at('2026-01-15', level=2)
        self.assertEqual(result['matches']['total'], 1)
        source = result['matches']['items'][0]['related']['sources']['items'][0]
        self.assertEqual(source['date'], '2026-03-01')
        self.assertEqual(current.build['source_revision'], self.after)
        self.assertEqual(current.valid_at('2026-03-01')['outside_recorded_intervals'], 1)

    def test_as_of_build_equals_the_exact_selected_revision_build(self):
        selected = compile_revision(self.repo, self.after, known_at='2026-02-15T00:00:00Z')
        self.assertEqual(selected, compile_revision(self.repo, self.before))
        self.assertEqual(compile_revision(self.repo, self.after), compile_revision(self.repo, self.after))

    def test_invalid_or_unavailable_knowledge_time_is_not_guessed(self):
        for at in ('2026-02-15', '2026-02-15T12:00:00', '2025-01-01T00:00:00Z'):
            with self.subTest(at=at), self.assertRaises((Invalid, ValueError)):
                knowledge_revision(self.repo, self.after, at)

    def test_retired_claims_remain_visible_at_their_recorded_valid_time(self):
        cid = canonical_id('RUN-' + '1' * 32, 'claims', 'c1')
        path = f'claims/{cid}.yaml'
        self.state[path]['state'] = 'retired'
        mid = 'M-' + '3' * 32
        self.state[f'maintenance/{mid}.yaml'] = {
            'schema_version': '1.0', 'id': mid, 'status': 'completed', 'base_commit': self.after,
            'created_at': '2026-05-01T12:00:00Z', 'claim_ids': [cid], 'reviewed_claim_ids': [cid],
            'touched_files': [path], 'findings': ['Synthetic retirement.'], 'deferred': [], 'no_change_reason': None,
        }
        retired = self.commit(self.state, '2026-05-01T12:00:00Z')
        current, _ = self.reader(compile_revision(self.repo, retired), 'retired')
        self.assertEqual(current.valid_at('2026-01-15')['matches']['items'][0]['record']['state'], 'retired')
        self.assertEqual(self.state[path]['uncertainty'], 'high')

    def test_unknown_and_disputed_dates_have_a_separate_bounded_result_group(self):
        legacy = contribution(token='4' * 32)
        legacy['claims'][0]['statement'] = 'Another synthetic unscoped statement.'
        self.state.update(state_for(legacy))
        self.state.update(plan_admission(self.state, legacy['id'], decisions(legacy), ROOT))
        recorded = self.commit(self.state, '2026-05-01T12:00:00Z')
        query, _ = self.reader(compile_revision(self.repo, recorded), 'unknown')
        result = query.valid_at('2026-01-15', limit=1)
        self.assertEqual(result['matches']['total'], 1)
        self.assertEqual(result['unresolved']['total'], 1)
        self.assertEqual(result['unresolved']['items'][0]['temporal_reason'], 'not_recorded')

    def test_cli_valid_at_and_known_at_build(self):
        folder = Path(self.temporary.name) / 'cli'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_knowledge.py'), '--repo', str(self.repo),
                                 '--revision', self.after, '--known-at', '2026-02-15T00:00:00Z', '--output', str(folder)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['source_revision'], self.before)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/query_knowledge.py'), '--package', str(folder),
                                 'valid-at', '2026-01-15'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['unresolved']['total'], 0)


if __name__ == '__main__':
    unittest.main()
