"""Opt-in mechanical admission of producer-verified contributions.

`fixtures/connector-v4-verified.json` is a connector v4 export written by the producer's
own exporter from its synthetic test sources, with the producer's name replaced by a
neutral one. It carries two supported claims, a within-run dependency, one withheld
claim and an auditor uncertainty review. No research or real world data.
"""
from __future__ import annotations
import copy
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from scripts.model import Invalid, load_state, validate_delta, validate_state
from scripts.verified_admission import CONNECTION_REASON, VERDICT_REASON, enabled, plan_verified, statement_sha256, verified
from scripts.world_control import canonical_id, main, plan_admission
from test_model import ROOT, admitted, contribution, decisions, state_for, write_state

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'connector-v4-verified.json'


def bundle(token=None):
    """The connector v4 export, optionally under another run ID."""
    p = json.loads(FIXTURE.read_text(encoding='utf-8'))
    if token:
        p['id'] = 'RUN-' + token * 32
    return p


def receipt(state, p):
    return state[f"briefs/closed/{p['id'].replace('RUN-', 'BC-')}.yaml"]


def mechanically_admitted(p, base=None):
    state = copy.deepcopy(base or {})
    state.update(state_for(p))
    state.update(plan_verified(state, p['id'], ROOT))
    return state


def agent_admitted(p):
    state = state_for(p)
    state.update(plan_admission(state, p['id'], decisions(p), ROOT))
    return state


def readmit_withheld(p, verdict=True):
    """Put the withheld claim back as candidate c3, mapped to its producer ID."""
    meta = p['method_metadata']
    withheld = meta['withheld_claims'][0]
    statement = withheld['claim']['text']
    p['claims'].append(dict(copy.deepcopy(p['claims'][1]), id='c3', statement=statement))
    meta['id_map']['claims'][withheld['claim']['id']] = 'c3'
    if verdict:  # A supported verdict bound to its statement, as if the producer had not withheld it.
        check = dict(withheld['final_check'], assessment='supported', statement_sha256=statement_sha256(statement))
        meta['claim_metadata']['c3'] = dict(meta['claim_metadata']['c2'], final_verdict='supported', final_check=check,
                                            statement_sha256=check['statement_sha256'])
    return p


def delta(before, after, opt_in=True):
    """PR delta validation with one resolvent.yaml on base and head; None leaves it out."""
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        for root, state in ((Path(a), before), (Path(b), after)):
            write_state(root, state)
            if opt_in is not None:
                (root / 'resolvent.yaml').write_text(f'verified_contributions: {str(opt_in).lower()}\n')
        validate_delta(Path(b), Path(a), after)


class VerifiedAdmissionTests(unittest.TestCase):
    def test_a_connector_v4_bundle_is_admitted_with_its_recorded_verdicts(self):
        p = bundle(); original = copy.deepcopy(p)
        self.assertTrue(verified(p))
        state = mechanically_admitted(p)
        validate_state(state, ROOT, True)  # compiler.py --require-closure
        delta({}, state)  # World model integrity with the opt-in on
        closure = receipt(state, p)
        ids = {local: canonical_id(p['id'], 'claims', local) for local in ('c1', 'c2')}
        self.assertEqual([(d['candidate_id'], d['disposition'], d['claim_id']) for d in closure['claim_dispositions']],
                         [('c1', 'created', ids['c1']), ('c2', 'created', ids['c2'])])
        verdicts = {local: p['method_metadata']['claim_metadata'][local]['final_check']['reason'].strip() for local in ids}
        self.assertEqual([d['reason'] for d in closure['claim_dispositions']],
                         [VERDICT_REASON + ' Recorded verdict: ' + verdicts[local] for local in ('c1', 'c2')])
        self.assertEqual({(r['outcome'], r['reason'], tuple(r['considered_claim_ids'])) for r in closure['connection_review']},
                         {('deferred', CONNECTION_REASON, ())})
        self.assertEqual(len(closure['follow_up_gaps']), 1)
        self.assertEqual(closure['schema_version'], '1.0')
        self.assertNotIn('model_operations', closure)
        # Each candidate keeps its exported class and grade; the auditor's review stays preserved metadata.
        fields = ('statement', 'class', 'uncertainty')
        admitted_claims = [state[f"claims/{ids[c['id']]}.yaml"] for c in p['claims']]
        self.assertEqual([[c[f] for f in fields] for c in admitted_claims], [[c[f] for f in fields] for c in p['claims']])
        graph = [record for path, record in state.items() if path.startswith('graph/')]
        self.assertEqual([(r['from'], r['to'], r['type']) for r in graph], [(ids['c1'], ids['c2'], 'dependency')])
        withheld = p['method_metadata']['withheld_claims'][0]['claim']['text']
        self.assertNotIn(withheld, json.dumps([r for path, r in state.items() if not path.startswith('input-artefacts/')]))
        self.assertEqual(state[f"input-artefacts/{p['id']}.json"], original)
        self.assertEqual(plan_verified(state, p['id'], ROOT), {})

    def test_a_claim_without_a_current_supported_verdict_is_refused(self):
        def no_verdict(p):
            entry = p['method_metadata']['claim_metadata']['c2']
            for field in ('final_verdict', 'final_check', 'statement_sha256', 'claim_snapshot_sha256'):
                del entry[field]

        def unsupported(p):
            p['method_metadata']['claim_metadata']['c2']['final_verdict'] = 'correction_needed'

        def unsupported_check(p):
            p['method_metadata']['claim_metadata']['c2']['final_check']['assessment'] = 'unresolved'

        def stale_verdict_hash(p):  # The statement changed after its verdict was recorded.
            p['claims'][1]['statement'] += ' Edited after verification.'

        def stale_check_hash(p):
            p['method_metadata']['claim_metadata']['c2']['final_check']['statement_sha256'] = '0' * 64

        def another_claims_verdict(p):
            entries = p['method_metadata']['claim_metadata']
            entries['c2']['final_check'] = dict(entries['c1']['final_check'], statement_sha256=entries['c2']['statement_sha256'])

        for change in (no_verdict, unsupported, unsupported_check, stale_verdict_hash, stale_check_hash, another_claims_verdict):
            p = bundle(); change(p)
            with self.subTest(change=change.__name__):
                with self.assertRaisesRegex(Invalid, 'c2 lacks a current supported verdict bound to its statement'):
                    mechanically_admitted(p)
                # With the opt-in on, an agent admission of the same contribution fails CI too.
                with self.assertRaisesRegex(Invalid, 'c2 lacks a current supported verdict bound to its statement'):
                    delta({}, agent_admitted(p))

    def test_a_withheld_claim_is_never_admitted(self):
        p = readmit_withheld(bundle())
        with self.assertRaisesRegex(Invalid, 'withheld claims stay out'):
            mechanically_admitted(p)
        with self.assertRaisesRegex(Invalid, 'withheld claims stay out'):
            delta({}, agent_admitted(p))
        # Without a forged verdict, the withheld claim has no supported verdict at all.
        with self.assertRaisesRegex(Invalid, 'c3 lacks a current supported verdict'):
            mechanically_admitted(readmit_withheld(bundle(), verdict=False))
        for field, value in (('supported_claims', 3), ('withheld_claims', 0)):
            p = bundle(); p['method_metadata']['verification'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(Invalid, 'counts differ'):
                mechanically_admitted(p)
        p = bundle(); del p['method_metadata']['withheld_claims']
        with self.assertRaisesRegex(Invalid, 'lists withheld claims'):
            mechanically_admitted(p)

    def test_ci_accepts_only_the_exact_mechanical_delta(self):
        p = bundle(); state = mechanically_admitted(p)
        cid = canonical_id(p['id'], 'claims', 'c2')

        def reason(s):
            receipt(s, p)['claim_dispositions'][1]['reason'] = 'An agent judgment.'

        def statement(s):
            s[f'claims/{cid}.yaml']['statement'] += ' Rewritten.'

        def connection(s):
            receipt(s, p)['connection_review'][1].update(outcome='no_justified_connection', reason='An agent judgment.')

        for forge in (reason, statement, connection):
            forged = copy.deepcopy(state); forge(forged)
            with self.subTest(forge=forge.__name__), self.assertRaisesRegex(Invalid, 'exactly its mechanical admission'):
                delta({}, forged)
        # Agent decisions, however reasonable, are not a mechanical admission of a verified contribution.
        with self.assertRaisesRegex(Invalid, 'exactly its mechanical admission'):
            delta({}, agent_admitted(p))
        other = contribution('source_material', '6' * 32); other['claims'][0]['statement'] = 'Another synthetic value is 8.'
        both = copy.deepcopy(state); both.update(state_for(other))
        both.update(plan_admission(both, other['id'], decisions(other), ROOT))
        with self.assertRaisesRegex(Invalid, 'in its own delta'):
            delta({}, both)

    def test_the_world_model_integrity_job_checks_the_opt_in_path(self):
        from scripts import compiler

        def integrity(after):
            """The CI job's own command: base-branch policy over the proposed state."""
            with tempfile.TemporaryDirectory() as policy, tempfile.TemporaryDirectory() as candidate:
                for root, state in ((Path(policy), {}), (Path(candidate), after)):
                    shutil.copytree(ROOT / 'docs', root / 'docs')
                    (root / 'resolvent.yaml').write_text('verified_contributions: true\n')
                    write_state(root, state)
                err = io.StringIO()
                argv = ['compiler.py', '--root', candidate, '--policy-root', policy, '--base', policy, '--require-closure']
                with mock.patch('sys.argv', argv), redirect_stdout(io.StringIO()), redirect_stderr(err):
                    return compiler.main(), err.getvalue()

        self.assertEqual(integrity(mechanically_admitted(bundle())), (0, ''))
        unverified = bundle(); del unverified['method_metadata']['claim_metadata']['c2']['final_check']
        code, err = integrity(agent_admitted(unverified))
        self.assertEqual(code, 1)
        self.assertIn('c2 lacks a current supported verdict', err)
        code, err = integrity(agent_admitted(readmit_withheld(bundle())))
        self.assertEqual(code, 1)
        self.assertIn('withheld claims stay out', err)

    def test_a_moved_base_requires_a_rebuild_on_it(self):
        p = bundle(); proposed = mechanically_admitted(p)
        earlier = bundle('4'); del earlier['method_metadata']['verification']
        base = admitted(earlier)  # Main admitted the same claims, with the same class and grade, through review.
        moved = copy.deepcopy(base); moved.update(proposed)
        with self.assertRaisesRegex(Invalid, 'exactly its mechanical admission'):
            delta(base, moved)
        rebuilt = mechanically_admitted(p, base)
        delta(base, rebuilt)
        targets = [canonical_id(earlier['id'], 'claims', local) for local in ('c1', 'c2')]
        self.assertEqual([(d['disposition'], d['claim_id']) for d in receipt(rebuilt, p)['claim_dispositions']],
                         [('merged', target) for target in targets])
        self.assertEqual([rebuilt[f'claims/{target}.yaml']['uncertainty'] for target in targets],
                         [c['uncertainty'] for c in p['claims']])

    def test_with_the_opt_in_off_nothing_changes(self):
        p = bundle()
        unverified = bundle(); del unverified['method_metadata']['claim_metadata']['c2']['final_verdict']
        for opt_in in (None, False):
            with self.subTest(opt_in=opt_in):
                # Admission and its independent review stay the path; CI adds no verified check.
                for state in (agent_admitted(p), agent_admitted(unverified), mechanically_admitted(p)):
                    delta({}, state, opt_in)
        # A PR cannot turn the opt-in on for itself: the setting is not model data.
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            state = mechanically_admitted(p)
            write_state(Path(b), state)
            (Path(a) / 'resolvent.yaml').write_text('verified_contributions: false\n')
            (Path(b) / 'resolvent.yaml').write_text('verified_contributions: true\n')
            with self.assertRaisesRegex(Invalid, 'Separate governance/code changes'):
                validate_delta(Path(b), Path(a), state)

    def test_the_opt_in_is_an_explicit_resolvent_yaml_setting(self):
        self.assertFalse(enabled(ROOT))  # The template ships with it off.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(enabled(root))
            for text, expected in ((b'project: Synthetic\n', False), (b'verified_contributions: false\n', False),
                                   (b'verified_contributions: true\n', True), (b'- not a mapping\n', False),
                                   (b'project: \xe9\n', False)):
                (root / 'resolvent.yaml').write_bytes(text)
                with self.subTest(text=text):
                    self.assertIs(enabled(root), expected)
            (root / 'resolvent.yaml').write_text('verified_contributions: "true"\n')
            with self.assertRaisesRegex(Invalid, 'must be true or false'):
                enabled(root)

    def test_other_contributions_keep_agent_admission(self):
        p = contribution('source_material', '7' * 32)
        self.assertFalse(verified(p))
        with self.assertRaisesRegex(Invalid, 'needs a source_material contribution'):
            plan_verified(state_for(p), p['id'], ROOT)
        delta({}, admitted(p))
        later = bundle('8'); later['method_metadata']['verification']['version'] = 2
        self.assertFalse(verified(later))
        delta({}, agent_admitted(later))
        other_route = bundle(); other_route['input_method'] = 'conversation'
        self.assertFalse(verified(other_route))

    def test_a_contribution_with_every_claim_withheld_closes_without_claims(self):
        p = bundle('9'); meta = p['method_metadata']
        p['claims'], p['connectors'] = [], []
        p['handoff']['no_claims_reason'] = 'Synthetic: verification withheld every candidate.'
        meta['id_map']['claims'], meta['claim_metadata'] = {}, {}
        meta['verification']['supported_claims'] = 0
        state = mechanically_admitted(p)
        validate_state(state, ROOT, True)
        delta({}, state)
        closure = receipt(state, p)
        self.assertEqual((closure['claim_dispositions'], closure['connection_review'], closure['follow_up_gaps']), ([], [], []))

    def test_writer_command_admits_only_where_the_world_opts_in(self):
        p = bundle()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'docs', root / 'docs')  # The writer reads the world's own schemas.
            write_state(root, state_for(p))
            source = f"input-artefacts/{p['id']}.json"

            def run(*args):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch('sys.argv', ['world_control.py', source, '--root', directory, *args]), \
                        redirect_stdout(out), redirect_stderr(err):
                    try:
                        code = main()
                    except SystemExit as stop:
                        code = stop.code
                return code, out.getvalue(), err.getvalue()

            self.assertEqual(run('--verified', '--decisions', 'x.json')[0], 2)
            for settings in (None, 'verified_contributions: false\n'):
                if settings:
                    (root / 'resolvent.yaml').write_text(settings)
                with self.subTest(settings=settings):
                    code, _, err = run('--verified', '--apply')
                    self.assertEqual(code, 1)
                    self.assertIn('Mechanical admission is off in this world', err)
                    self.assertEqual(load_state(root), state_for(p))
            (root / 'resolvent.yaml').write_text('verified_contributions: true\n')
            code, out, _ = run('--verified')
            self.assertEqual((code, json.loads(out)['mode']), (0, 'dry_run'))
            self.assertEqual(load_state(root), state_for(p))
            code, out, _ = run('--verified', '--apply')
            self.assertEqual((code, json.loads(out)['mode']), (0, 'applied'))
            written = load_state(root)
            validate_state(written, ROOT, True)
            self.assertEqual(written, mechanically_admitted(p) | {
                f"briefs/closed/{p['id'].replace('RUN-', 'BC-')}.yaml": receipt(written, p)})
            self.assertTrue(json.loads(run('--verified')[1])['already_processed'])


if __name__ == '__main__':
    unittest.main()
