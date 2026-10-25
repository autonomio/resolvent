"""Synthetic compiled-view fixtures; no test data enters canonical directories."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts.build_knowledge import ROOT, build, compile_revision
from scripts.model import CANONICAL_ROOTS, Invalid, family
from scripts.world_control import canonical_id
from test_model import admitted, contribution, state_for, write_state


def linked_state() -> dict[str, dict]:
    proposal = contribution()
    proposal['sources'][0]['access'] = 'not_retrieved'
    second = copy.deepcopy(proposal['claims'][0])
    second.update(id='c2', statement='A second synthetic value depends on the first.',
                  evidence_ids=['e2'])
    proposal['claims'].append(second)
    premise = copy.deepcopy(proposal['evidence'][0])
    premise.update(id='e2', kind='derivation', premise_claim_ids=['c1'])
    proposal['evidence'].append(premise)
    proposal['connectors'] = [
        {'id': 'r1', 'from': 'c2', 'to': 'c1', 'type': 'dependency',
         'spec': 'structural:strong:inward', 'reason': 'Synthetic dependency.',
         'uncertainty': 'high', 'evidence_ids': ['e2']},
        {'id': 'r2', 'from': 'c1', 'to': 'c2', 'type': 'coupling',
         'spec': 'narrative:weak:balanced', 'reason': 'Synthetic contextual influence.',
         'uncertainty': 'high', 'evidence_ids': ['e1']},
    ]
    proposal['questions'] = [{'id': 'q1', 'question': 'Synthetic unresolved question?',
                               'claim_ids': ['c1', 'c2']}]
    return admitted(proposal)


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / 'repo'
        self.repo.mkdir()
        self.git('init', '-q', '--initial-branch=main')
        (self.repo / '.gitignore').write_text('.resolvent/\n')

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ['git', '-C', str(self.repo), *args], text=True,
            stderr=subprocess.PIPE).strip()

    def commit(self, state: dict[str, dict]) -> str:
        write_state(self.repo, state)
        self.git('add', '.')
        self.git('-c', 'user.name=Synthetic test', '-c', 'user.email=test@example.invalid',
                 'commit', '-qm', 'Synthetic fixture', '--allow-empty')
        return self.git('rev-parse', 'HEAD')

    def package(self, state=None) -> tuple[str, dict[str, bytes], dict, dict]:
        commit = self.commit(state if state is not None else linked_state())
        package = compile_revision(self.repo, commit)
        return commit, package, json.loads(package['manifest.json']), json.loads(package['knowledge.json'])

    def maintenance(self, state: dict, status='completed') -> dict:
        claim_ids = [record['id'] for path, record in state.items() if path.startswith('claims/')]
        mid = 'M-' + '3' * 32
        return {
            'schema_version': '1.0', 'id': mid, 'status': status,
            'base_commit': 'a' * 40, 'created_at': '2026-01-01T12:00:00Z',
            'claim_ids': claim_ids,
            'reviewed_claim_ids': list(claim_ids) if status == 'completed' else [],
            'touched_files': [], 'findings': [], 'deferred': [],
            'no_change_reason': 'Synthetic review.' if status == 'completed' else None,
        }

    def test_empty_revision_has_explicit_empty_projections(self):
        commit, package, manifest, knowledge = self.package({})
        self.assertEqual(set(package), {'manifest.json', 'knowledge.json'})
        self.assertEqual(manifest['source_revision'], commit)
        self.assertEqual(knowledge['records'], {group: {} for group in CANONICAL_ROOTS})
        self.assertEqual(knowledge['provenance'], {})
        self.assertTrue(manifest['derived'])
        self.assertTrue(knowledge['derived'])
        self.assertTrue(manifest['validation']['require_closure'])

    def test_canonical_fields_and_full_provenance_survive(self):
        state = linked_state()
        _, _, manifest, knowledge = self.package(state)
        for path, record in state.items():
            group = family(path)
            if group in CANONICAL_ROOTS:
                self.assertEqual(knowledge['records'][group][record['id']], record)
                self.assertEqual(knowledge['record_paths'][record['id']], path)
            else:
                self.assertEqual(knowledge['provenance'][path], record)
        self.assertEqual(len(knowledge['records']['claims']), 2)
        self.assertEqual(manifest['validation']['records']['claims'], 2)
        source = next(iter(knowledge['records']['sources'].values()))
        self.assertEqual(source['access'], 'not_retrieved')

    def test_reverse_links_cover_sources_claims_premises_connectors_and_questions(self):
        _, _, _, knowledge = self.package()
        run = 'RUN-' + '1' * 32
        c1, c2 = [canonical_id(run, 'claims', key) for key in ('c1', 'c2')]
        e1, e2 = [canonical_id(run, 'evidence', key) for key in ('e1', 'e2')]
        r1, r2 = [canonical_id(run, 'graph', key) for key in ('r1', 'r2')]
        sid = canonical_id(run, 'sources', 's1')
        qid = canonical_id(run, 'questions', 'q1')
        reverse = knowledge['reverse_links']
        self.assertEqual(reverse['sources'][sid]['evidence_ids'], sorted([e1, e2]))
        self.assertEqual(reverse['evidence'][e1], {'claim_ids': [c1], 'connector_ids': [r2]})
        self.assertEqual(reverse['evidence'][e2], {'claim_ids': [c2], 'connector_ids': [r1]})
        self.assertEqual(reverse['claims'][c1], {
            'incoming_connector_ids': [r1], 'outgoing_connector_ids': [r2],
            'premise_evidence_ids': [e2], 'question_ids': [qid],
        })
        self.assertEqual(reverse['claims'][c2]['question_ids'], [qid])

    def test_retired_records_and_relationship_types_are_preserved(self):
        state = linked_state()
        touched = []
        for path, record in state.items():
            if family(path) in ('claims', 'graph', 'questions'):
                record['state'] = 'retired'
                touched.append(path)
        maintenance = self.maintenance(state)
        maintenance.update(touched_files=touched, findings=['Synthetic retirements.'],
                           no_change_reason=None)
        state['maintenance/' + maintenance['id'] + '.yaml'] = maintenance
        _, _, _, knowledge = self.package(state)
        for group in ('claims', 'graph', 'questions'):
            self.assertTrue(all(record['state'] == 'retired'
                                for record in knowledge['records'][group].values()))
        self.assertEqual({record['type'] for record in knowledge['records']['graph'].values()},
                         {'dependency', 'coupling'})

    def test_input_and_artifact_hashes_are_independently_verifiable(self):
        state = linked_state()
        commit, package, manifest, _ = self.package(state)
        self.assertEqual(set(manifest['input_files']), set(state))
        for path, expected in manifest['input_files'].items():
            contents = subprocess.check_output(['git', '-C', str(self.repo), 'show', f'{commit}:{path}'])
            self.assertEqual(hashlib.sha256(contents).hexdigest(), expected)
        normalized = json.dumps(manifest['input_files'], sort_keys=True, separators=(',', ':'),
                                ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.assertEqual(hashlib.sha256(normalized).hexdigest(), manifest['input_tree_sha256'])
        for filename, integrity in manifest['artifacts'].items():
            self.assertEqual(hashlib.sha256(package[filename]).hexdigest(), integrity['sha256'])
            self.assertEqual(len(package[filename]), integrity['bytes'])
            self.assertNotEqual(hashlib.sha256(package[filename] + b' ').hexdigest(), integrity['sha256'])
        self.assertIn('scripts/model.py', manifest['validation']['policy_files'])
        self.assertIn('docs/schemas/claims.schema.json', manifest['validation']['policy_files'])

    def test_repeated_builds_across_clones_and_output_paths_are_identical(self):
        commit, expected, _, _ = self.package()
        clone = Path(self.temporary.name) / 'clone'
        subprocess.run(['git', 'clone', '-q', '--no-hardlinks', str(self.repo), str(clone)], check=True)
        for name, repo in (('one', self.repo), ('two', clone)):
            output = Path(self.temporary.name) / name
            build(repo, commit, output)
            actual = {path.name: path.read_bytes() for path in output.iterdir()}
            self.assertEqual(actual, expected)
            self.assertNotIn(str(repo).encode(), actual['manifest.json'])

    def test_pinned_revision_ignores_dirty_worktree_and_later_commits(self):
        commit, expected, _, _ = self.package()
        path = next(self.repo.glob('claims/*.yaml'))
        path.write_text('not: valid canonical data\n')
        (self.repo / 'scripts').mkdir()
        (self.repo / 'scripts/model.py').write_text('raise RuntimeError("must not execute")\n')
        self.assertEqual(compile_revision(self.repo, commit), expected)
        later = self.commit({})
        self.assertNotEqual(later, commit)
        self.assertEqual(compile_revision(self.repo, commit), expected)
        with self.assertRaises(Invalid):
            compile_revision(self.repo, later)

    def test_git_replace_cannot_change_a_pinned_revision(self):
        state = linked_state()
        commit, expected, _, _ = self.package(state)
        next(record for path, record in state.items()
             if path.startswith('claims/'))['statement'] = 'Different synthetic proposition.'
        replacement = self.commit(state)
        self.git('replace', commit, replacement)
        self.assertEqual(compile_revision(self.repo, commit), expected)

    def test_missing_partial_clone_objects_cannot_trigger_a_fetch(self):
        state = linked_state()
        commit = self.commit(state)
        donor = Path(self.temporary.name) / 'donor'
        shutil.copytree(self.repo, donor)
        path = next(path for path in state if path.startswith('claims/'))
        oid = self.git('rev-parse', f'{commit}:{path}')
        object_path = self.repo / '.git/objects' / oid[:2] / oid[2:]
        object_path.unlink()
        self.git('config', 'remote.origin.url', str(donor))
        self.git('config', 'remote.origin.promisor', 'true')
        with self.assertRaises(Invalid):
            compile_revision(self.repo, commit)
        self.assertFalse(object_path.exists())

    def test_rejected_and_deferred_candidates_never_become_claims(self):
        from scripts.world_control import plan_admission
        from test_model import decisions
        for action in ('reject', 'defer'):
            with self.subTest(action=action):
                proposal = contribution()
                state = state_for(proposal)
                state.update(plan_admission(state, proposal['id'], decisions(proposal, action), ROOT))
                commit = self.commit(state)
                knowledge = json.loads(compile_revision(self.repo, commit)['knowledge.json'])
                self.assertEqual(knowledge['records']['claims'], {})
                closure = next(record for path, record in knowledge['provenance'].items()
                               if path.startswith('briefs/closed/'))
                self.assertEqual(closure['claim_dispositions'][0]['disposition'],
                                 'rejected' if action == 'reject' else 'deferred')

    def test_pending_contribution_fails_before_output_is_created(self):
        commit = self.commit(state_for(contribution()))
        output = self.repo / '.resolvent' / 'pending'
        with self.assertRaisesRegex(Invalid, 'Awaiting admission'):
            build(self.repo, commit, output)
        self.assertFalse(output.parent.exists())

    def test_pending_maintenance_fails(self):
        state = linked_state()
        maintenance = self.maintenance(state, status='pending')
        state['maintenance/' + maintenance['id'] + '.yaml'] = maintenance
        commit = self.commit(state)
        with self.assertRaisesRegex(Invalid, 'Awaiting maintenance'):
            compile_revision(self.repo, commit)

    def test_invalid_state_stale_closure_and_unprovenanced_records_fail(self):
        for fault in ('missing evidence', 'stale closure', 'missing provenance'):
            with self.subTest(fault=fault):
                state = linked_state()
                if fault == 'missing evidence':
                    next(record for path, record in state.items()
                         if path.startswith('claims/'))['evidence_ids'] = ['missing']
                elif fault == 'stale closure':
                    next(record for path, record in state.items()
                         if path.startswith('input-artefacts/'))['title'] = 'Changed after closure'
                else:
                    state = {path: record for path, record in state.items()
                             if family(path) in CANONICAL_ROOTS}
                    shutil.rmtree(self.repo / 'briefs', ignore_errors=True)
                    shutil.rmtree(self.repo / 'input-artefacts', ignore_errors=True)
                commit = self.commit(state)
                with self.assertRaises(Invalid):
                    compile_revision(self.repo, commit)

    def test_symlinks_in_git_data_are_rejected(self):
        self.commit({})
        (self.repo / 'claims').mkdir()
        (self.repo / 'claims' / ('C-' + '1' * 32 + '.yaml')).symlink_to('../.gitignore')
        commit = self.commit({})
        with self.assertRaisesRegex(Invalid, 'Only regular data files'):
            compile_revision(self.repo, commit)

    def test_invalid_or_option_like_revisions_fail(self):
        self.commit({})
        for revision in ('does-not-exist', '--all', 'HEAD:claims'):
            with self.subTest(revision=revision), self.assertRaises(Invalid):
                compile_revision(self.repo, revision)

    def test_existing_or_canonical_outputs_are_rejected_without_mutation(self):
        commit = self.commit({})
        existing = self.repo / '.resolvent' / 'existing'
        existing.mkdir(parents=True)
        marker = existing / 'marker'
        marker.write_bytes(b'keep')
        for output in (existing, self.repo / 'claims' / 'compiled', self.repo / 'build'):
            with self.subTest(output=output), self.assertRaises(Invalid):
                build(self.repo, commit, output)
        self.assertEqual(marker.read_bytes(), b'keep')
        self.assertFalse((self.repo / 'claims').exists())
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_io_failure_does_not_expose_a_partial_package(self):
        commit = self.commit({})
        output = self.repo / '.resolvent' / 'build'
        with mock.patch.object(Path, 'rename', side_effect=OSError('Synthetic I/O failure')):
            with self.assertRaisesRegex(OSError, 'Synthetic I/O failure'):
                build(self.repo, commit, output)
        self.assertFalse(output.exists())
        self.assertEqual(list(output.parent.iterdir()), [])

    def test_cli_builds_under_ignored_directory(self):
        commit = self.commit({})
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/build_knowledge.py'), '--repo', str(self.repo),
             '--revision', commit, '--output', '.resolvent/build'],
            cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        manifest = (self.repo / '.resolvent/build/manifest.json').read_bytes()
        self.assertEqual(report['manifest_sha256'], hashlib.sha256(manifest).hexdigest())
        self.assertEqual(report['source_revision'], commit)
        self.assertEqual(self.git('status', '--porcelain'), '')


if __name__ == '__main__':
    unittest.main()
