"""Synthetic recent-window fixtures: exact additions in, judgments stay external."""
from __future__ import annotations

import copy
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts.build_knowledge import compile_revision
from scripts.gap_finder import recent_workset, workset as weekly_workset
from scripts.model import Invalid, load_state, validate_delta, validate_state
from scripts.model_operations import model_digest
from scripts.query_knowledge import Knowledge
from scripts.recent_additions import WINDOW_FIELDS, window
from scripts.signal_contract import signal_id
from scripts.world_control import canonical_id, plan_admission, plan_maintenance
from test_change_signals import signal
from test_model import ROOT, contribution, decisions, state_for, write_state

T0, T1 = '2026-01-01T00:00:00Z', '2026-01-02T12:00:00Z'
NIGHT1, COMPLETED = '2026-01-03T06:00:00Z', '2026-01-03T07:00:00Z'
TRIAL = {'kind': 'publication', 'title': 'Synthetic trial report', 'uri': 'https://example.invalid/synthetic-trial',
         'excerpt': 'Synthetic compound K lowered fever in the fixture cohort.', 'access': 'inspected'}


def run(token, entries, questions=(), schema='1.0'):
    """One synthetic run: each entry is (statement, uncertainty, source fields) with its own evidence."""
    p = contribution(token=token * 32)
    p['schema_version'] = schema
    source, evidence, claim = (copy.deepcopy(p[group][0]) for group in ('sources', 'evidence', 'claims'))
    p.update(sources=[], evidence=[], claims=[], questions=copy.deepcopy(list(questions)))
    for number, (statement, uncertainty, fields) in enumerate(entries, 1):
        p['sources'].append({**copy.deepcopy(source), 'id': f's{number}', **copy.deepcopy(fields)})
        p['evidence'].append({**copy.deepcopy(evidence), 'id': f'e{number}', 'source_ids': [f's{number}'],
                              'summary': f'Synthetic report {number} in run {token}.'})
        p['claims'].append({**copy.deepcopy(claim), 'id': f'c{number}', 'statement': statement,
                            'uncertainty': uncertainty, 'evidence_ids': [f'e{number}']})
    return p


def ident(p, group, local):
    return canonical_id(p['id'], group, local)


FIRST = run('1', [('Synthetic compound K lowers fever in adults.', 'medium', TRIAL),
                  ('Synthetic lake levels rose during the fixture decade.', 'high', {})],
            [{'id': 'q1', 'question': 'Does synthetic compound K lower fever?', 'claim_ids': ['c1']}])
X, Y = ident(FIRST, 'claims', 'c1'), ident(FIRST, 'claims', 'c2')
REUSE = dict(TRIAL, ancestry={'status': 'derived', 'parent_source_ids': [ident(FIRST, 'sources', 's1')],
                              'notes': ['Synthetic declared reuse of the earlier trial report.']})
# A restates X with a different grade (a real duplicate); B depends on X (a real connection candidate).
SECOND = run('2', [('Synthetic compound K lowers fever in adults.', 'high', REUSE),
                   ('Lower fever from synthetic compound K reduces dehydration risk in adults.', 'high', {})],
             [{'id': 'q1', 'question': 'What follows from synthetic fever reduction?', 'claim_ids': ['c2', X]}], '1.2')
A, B = ident(SECOND, 'claims', 'c1'), ident(SECOND, 'claims', 'c2')


def instant(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00'))


class RecentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'world'
        self.repo.mkdir()
        self.git('init', '-q')
        self.state = {}
        self.first = self.admit(FIRST, T0)
        self.second = self.admit(SECOND, T1)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()

    def commit(self, when):
        stamp = f"{int(instant(when).timestamp())} +0000"
        self.git('add', '-A')
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Synthetic test', '-c',
                        'user.email=test@example.invalid', 'commit', '-qm', 'Synthetic fixture'], check=True,
                       env={**os.environ, 'GIT_AUTHOR_DATE': stamp, 'GIT_COMMITTER_DATE': stamp})
        return self.git('rev-parse', 'HEAD')

    def admit(self, p, when):
        self.state.update(state_for(p))
        self.state.update(plan_admission(self.state, p['id'], decisions(p), ROOT))
        write_state(self.repo, self.state)
        return self.commit(when)

    def complete(self, record, when, operations=(), **fields):
        state = load_state(self.repo)
        state['maintenance/' + record['id'] + '.yaml'] = record
        decision = dict(expected_model_sha256=model_digest(state), model_operations=list(operations),
                        reviewed_claim_ids=record['claim_ids'], **fields)
        changes = plan_maintenance(state, record['id'], decision, ROOT)
        write_state(self.repo, changes)
        self.state.update(changes)
        return self.commit(when)

    def knowledge(self, revision='HEAD'):
        package = Path(tempfile.mkdtemp(dir=self.temp.name))
        for name, contents in compile_revision(self.repo, revision).items():
            (package / name).write_bytes(contents)
        return Knowledge(package), package

    def test_workset_contains_exactly_the_added_claims(self):
        record = recent_workset(self.repo, now=instant(NIGHT1))
        self.assertEqual(record['claim_ids'], sorted([A, B]))
        self.assertEqual(record['schema_version'], '1.3')
        self.assertEqual((record['base_commit'], record['created_at']), (self.second, NIGHT1))
        self.assertEqual(record['window'], {'start': 'hours', 'previous_workset_id': None, 'from_revision': self.first,
                                            'from_committed_at': T0, 'to_committed_at': T1, 'hours': 24})
        weekly = weekly_workset(self.repo)['claim_ids']
        self.assertTrue({X, Y} <= set(weekly))  # Never-reviewed and rotating claims stay weekly-only.
        self.assertFalse({X, Y} & set(record['claim_ids']))
        state = load_state(self.repo)
        state['maintenance/' + record['id'] + '.yaml'] = record
        validate_state(state, ROOT)
        with self.assertRaisesRegex(Invalid, 'Awaiting maintenance'):
            validate_state(state, ROOT, require_closure=True)

    def test_call_alone_supplies_a_duplicate_merge_and_a_connection(self):
        record = recent_workset(self.repo, now=instant(NIGHT1))
        query, _ = self.knowledge(record['base_commit'])
        response = query.recent(self.repo, at=record['created_at'])
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual({key: response['window'][key] for key in WINDOW_FIELDS}, record['window'])
        self.assertEqual(response['window']['to_revision'], record['base_commit'])
        self.assertEqual(response['decisions'], {'expected_model_sha256': query.model_sha256,
                                                 'reviewed_claim_ids': record['claim_ids']})
        added = {entry['id']: entry for entry in response['added']}
        self.assertEqual(sorted(added), record['claim_ids'])
        duplicate = next(target for target in added[A]['compare_with'] if target['id'] == X)
        self.assertTrue({'statement', 'class', 'temporal_scope', 'uncertainty', 'evidence_ids', 'source_ids',
                         'reasons', 'links', 'current_assessment'} <= set(duplicate))
        self.assertEqual(duplicate['reasons'], ['shared_source', 'wording_overlap'])
        self.assertEqual(duplicate['shared_source_ids'], [ident(FIRST, 'sources', 's1')])
        self.assertEqual((duplicate['statement'], duplicate['class'], duplicate['uncertainty']),
                         (added[A]['statement'], added[A]['class'], 'medium'))
        self.assertEqual(duplicate['temporal_scope'], added[A]['temporal_scope'])
        self.assertFalse(duplicate['added_in_window'])
        self.assertEqual(duplicate['links'], {'connectors': [], 'comparisons': [], 'premise_evidence_ids': []})
        reused = ident(SECOND, 'sources', 's1')
        self.assertEqual([source['id'] for source in added[A]['sources']], sorted([ident(FIRST, 'sources', 's1'), reused]))
        self.assertEqual(added[A]['added_in_window_ids'], sorted([ident(SECOND, 'evidence', 'e1'), reused]))
        self.assertEqual(added[A]['admissions'][0]['submission_id'], SECOND['id'])
        candidate = next(target for target in added[B]['compare_with'] if target['id'] == X)
        self.assertIn('same_question', candidate['reasons'])
        self.assertEqual(candidate['shared_question_ids'], [ident(SECOND, 'questions', 'q1')])
        self.assertEqual(set(added[B]['questions'][0]['claim_ids']), {B, X})
        # Wording-only matches are ranked and capped; a shared source is never capped.
        self.assertEqual([target['id'] for target in added[A]['compare_with']], [X, B, Y])
        for limit, kept, counts in ((1, [X, B], {'matches': 2, 'included': 1, 'omitted': 1}),
                                    (0, [X], {'matches': 2, 'included': 0, 'omitted': 2})):
            bounded = {entry['id']: entry for entry in query.recent(self.repo, at=NIGHT1, overlap_limit=limit)['added']}
            self.assertEqual([target['id'] for target in bounded[A]['compare_with']], kept)
            self.assertEqual(bounded[A]['wording_overlap'], counts)

        merge = {'id': 'merge1', 'kind': 'comparison', 'subject_ids': [A, X], 'outcome': 'equivalent',
                 'basis_ids': added[A]['evidence_ids'] + duplicate['evidence_ids'], 'supersedes': None,
                 'reason': 'Synthetic: the same proposition, class and temporal scope.'}
        grade = {'id': 'grade1', 'kind': 'reassessment', 'subject_ids': [X], 'basis_ids': added[A]['evidence_ids'],
                 'uncertainty': added[A]['uncertainty'], 'predecessors': {X: duplicate['current_assessment']},
                 'reason': 'Synthetic: settle the grades the merge joined.'}
        connector = {'id': 'R-' + 'c' * 32, 'from': B, 'to': X, 'type': 'dependency', 'spec': 'structural:moderate:inward',
                     'reason': 'Synthetic: the consequence depends on the effect.', 'uncertainty': 'high',
                     'evidence_ids': added[B]['evidence_ids'], 'state': 'active'}
        link = {'id': 'link1', 'kind': 'linkage', 'subject_ids': [B, X], 'basis_ids': added[B]['evidence_ids'],
                'record': connector, 'previous_sha256': None, 'reason': 'Synthetic justified connection.'}
        base = load_state(self.repo)
        pending = dict(base, **{'maintenance/' + record['id'] + '.yaml': record})
        decision = dict(response['decisions'], model_operations=[merge, grade, link],
                        findings=['Synthetic duplicate merged and connection added.'])
        for operations in ([grade], [dict(merge, subject_ids=[X, Y]), grade],
                           [merge, dict(grade, subject_ids=[Y], predecessors={Y: None})]):
            with self.subTest(operations=[op['id'] for op in operations]), self.assertRaisesRegex(Invalid, 'outside the selected'):
                plan_maintenance(pending, record['id'], dict(decision, model_operations=operations), ROOT)
        changes = plan_maintenance(pending, record['id'], decision, ROOT)
        self.assertEqual(sorted(changes), sorted(['claims/' + X + '.yaml', 'graph/' + connector['id'] + '.yaml',
                                                  'maintenance/' + record['id'] + '.yaml']))
        completed = changes['maintenance/' + record['id'] + '.yaml']
        self.assertEqual((completed['schema_version'], completed['window']), ('1.3', record['window']))
        after = dict(pending, **changes)
        validate_state(after, ROOT, require_closure=True)
        with tempfile.TemporaryDirectory() as before_dir, tempfile.TemporaryDirectory() as after_dir:
            write_state(Path(before_dir), base)
            write_state(Path(after_dir), after)
            validate_delta(Path(after_dir), Path(before_dir), after)
        write_state(self.repo, changes)
        self.commit(COMPLETED)
        query, _ = self.knowledge()
        self.assertEqual(query.lookup(A)['current_assessment']['status'], 'agreed')
        later = query.recent(self.repo, at='2026-01-03T08:00:00Z')
        self.assertEqual((later['window']['start'], later['window']['previous_workset_id']),
                         ('last_completed_recent_workset', record['id']))
        self.assertEqual((later['added'], later['decisions']['reviewed_claim_ids']), ([], []))
        self.assertIsNone(recent_workset(self.repo, now=instant('2026-01-03T08:00:00Z')))

    def test_missed_night_starts_at_the_last_completed_window(self):
        first = recent_workset(self.repo, now=instant(NIGHT1))
        self.complete(first, COMPLETED, no_change_reason='Synthetic pass found no justified change.')
        third = run('3', [('Synthetic river flow fell in the fixture spring.', 'high', {})])
        fourth = run('4', [('Synthetic soil moisture rose after the fixture rains.', 'high', {})])
        self.admit(third, '2026-01-04T12:00:00Z')
        self.admit(fourth, '2026-01-05T12:00:00Z')
        # No workset completed on the night of 2026-01-05; 24 hours alone would miss the third run.
        night = '2026-01-06T06:00:00Z'
        record = recent_workset(self.repo, now=instant(night))
        self.assertEqual(record['claim_ids'], sorted([ident(third, 'claims', 'c1'), ident(fourth, 'claims', 'c1')]))
        self.assertEqual(record['window'], {'start': 'last_completed_recent_workset', 'previous_workset_id': first['id'],
                                            'from_revision': first['base_commit'], 'from_committed_at': T1,
                                            'to_committed_at': '2026-01-05T12:00:00Z', 'hours': 24})
        query, _ = self.knowledge()
        response = query.recent(self.repo, at=night)
        self.assertEqual([entry['id'] for entry in response['added']], record['claim_ids'])
        self.assertEqual({key: response['window'][key] for key in WINDOW_FIELDS}, record['window'])

    def test_a_later_package_still_returns_exactly_the_workset(self):
        record = recent_workset(self.repo, now=instant(NIGHT1))
        later = run('3', [('Synthetic compound K lowers fever in older adults.', 'high', {})])
        self.admit(later, COMPLETED)  # Main advances and the workset branch is updated before the pass.
        query, _ = self.knowledge()
        response = query.recent(self.repo, at=record['created_at'], to=record['base_commit'])
        self.assertEqual({key: response['window'][key] for key in WINDOW_FIELDS}, record['window'])
        self.assertEqual(response['window']['to_revision'], record['base_commit'])
        self.assertEqual(response['decisions']['reviewed_claim_ids'], record['claim_ids'])
        entry = next(entry for entry in response['added'] if entry['id'] == A)
        target = next(target for target in entry['compare_with'] if target['id'] == ident(later, 'claims', 'c1'))
        self.assertFalse(target['added_in_window'])
        state = load_state(self.repo)
        state['maintenance/' + record['id'] + '.yaml'] = record
        decision = dict(response['decisions'], model_operations=[],
                        no_change_reason='Synthetic pass found no justified change.')
        self.assertIn('maintenance/' + record['id'] + '.yaml', plan_maintenance(state, record['id'], decision, ROOT))
        unrelated = subprocess.check_output(['git', '-C', str(self.repo), '-c', 'user.name=Synthetic test', '-c',
                                             'user.email=test@example.invalid', 'commit-tree', self.git('write-tree'),
                                             '-m', 'Unrelated history'], text=True).strip()
        with self.assertRaisesRegex(Invalid, 'ancestors'):
            query.recent(self.repo, at=NIGHT1, to=unrelated)

    def test_empty_windows_prepare_nothing(self):
        self.assertIsNone(recent_workset(self.repo, now=instant('2026-01-04T00:00:00Z')))
        query, _ = self.knowledge()
        response = query.recent(self.repo, at='2026-01-04T00:00:00Z')
        self.assertEqual((response['window']['from_revision'], response['added_total']), (self.second, 0))
        # History younger than the cutoff opens at the empty model, so nothing older is lost.
        young = recent_workset(self.repo, hours=48, now=instant('2026-01-02T18:00:00Z'))
        self.assertEqual(young['claim_ids'], sorted([A, B, X, Y]))
        self.assertEqual((young['window']['from_revision'], young['window']['from_committed_at']), (None, None))
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/gap_finder.py'), '--root', str(self.repo),
                                 '--recent', '--write'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('No claims were added in the recent window', result.stdout)
        self.assertFalse((self.repo / 'maintenance').exists() and any((self.repo / 'maintenance').glob('M-*.yaml')))

    def test_cli_matches_the_library_and_reads_only_git_objects(self):
        query, package = self.knowledge()
        command = [sys.executable, str(ROOT / 'scripts/query_knowledge.py'), '--package', str(package), 'recent',
                   '--repo', str(self.repo), '--at', NIGHT1]
        for flags, options in (([], {}), (['--to', self.first, '--hours', '48', '--overlap-limit', '1'],
                                          {'to': self.first, 'hours': 48, 'overlap_limit': 1})):
            result = subprocess.run(command + flags, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), query.recent(self.repo, at=NIGHT1, **options))
        (self.repo / 'claims' / (A + '.yaml')).write_text('Uncommitted edit.\n')
        self.assertEqual(query.recent(self.repo, at=NIGHT1)['added_total'], 2)
        with self.assertRaisesRegex(Invalid, 'Commit the world data'):
            recent_workset(self.repo, now=instant(NIGHT1))

    def test_unsupported_windows_fail_closed(self):
        for options in ({'hours': 0}, {'hours': 8761}, {'at': '2026-01-03'}):
            with self.subTest(options=options), self.assertRaises(Invalid):
                window(self.repo, 'HEAD', [], **{'at': NIGHT1, **options})
        shallow = Path(self.temp.name) / 'shallow'
        subprocess.run(['git', 'clone', '-q', '--depth', '1', self.repo.resolve().as_uri(), str(shallow)], check=True)
        with self.assertRaisesRegex(Invalid, 'shallow'):
            recent_workset(shallow, now=instant(NIGHT1))

    def test_recent_profile_requires_its_window_and_excludes_signal_triggers(self):
        record = recent_workset(self.repo, now=instant(NIGHT1))
        state = load_state(self.repo)
        path = 'maintenance/' + record['id'] + '.yaml'
        for mutate in (lambda r: r.pop('window'), lambda r: r.update(schema_version='1.2'),
                       lambda r: r['window'].update(start='last_completed_recent_workset'),
                       lambda r: r['window'].update(from_committed_at=None),
                       lambda r: r.update(trigger={'signal_id': signal_id(signal()), 'signal': signal()})):
            bad = copy.deepcopy(record)
            mutate(bad)
            with self.subTest(record=bad), self.assertRaises(Invalid):
                validate_state(dict(state, **{path: bad}), ROOT)

    def test_recent_completions_do_not_advance_weekly_rotation(self):
        active = ['C-' + format(number, '032x') for number in range(1, 81)]
        claims = {cid: {'id': cid, 'state': 'active'} for cid in active}
        records = {cid: {'status': 'completed', 'reviewed_claim_ids': [cid]} for cid in active}
        with patch('scripts.gap_finder.load_state', return_value={}), \
                patch('scripts.gap_finder.indexes', return_value={'claims': claims, 'maintenance': records}):
            first = weekly_workset(self.repo)['claim_ids']
            records['recent'] = {'status': 'completed', 'reviewed_claim_ids': [active[0]], 'window': {}}
            self.assertEqual(weekly_workset(self.repo)['claim_ids'], first)

    def test_nightly_schedule_is_opt_in_and_replaces_the_weekly_selection(self):
        workflow = yaml.load((ROOT / '.github/workflows/maintenance.yml').read_text(), Loader=yaml.BaseLoader)
        crons = [entry['cron'] for entry in workflow['on']['schedule']]
        self.assertEqual(len(crons), 2)
        job = workflow['jobs']['prepare']
        weekly, nightly = crons
        self.assertIn(f"github.event.schedule == '{weekly}' && vars.RESOLVENT_MAINTENANCE_SCHEDULE != 'nightly'", job['if'])
        self.assertIn(f"github.event.schedule == '{nightly}' && vars.RESOLVENT_MAINTENANCE_SCHEDULE == 'nightly'", job['if'])
        self.assertIn("github.event_name == 'workflow_dispatch'", job['if'])
        self.assertEqual(job['env']['MODE'], "${{ vars.RESOLVENT_MAINTENANCE_SCHEDULE == 'nightly' && 'recent' || 'weekly' }}")
        self.assertEqual(job['steps'][0]['with']['fetch-depth'], '0')
        script = next(step['run'] for step in job['steps'] if 'gap_finder.py' in step.get('run', ''))
        self.assertIn('python scripts/gap_finder.py --recent --write', script)
        self.assertIn('python scripts/gap_finder.py --write', script)


if __name__ == '__main__':
    unittest.main()
