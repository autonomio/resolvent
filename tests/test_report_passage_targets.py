"""Synthetic corrections to a frozen report in an accepted submission."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from test_model import ROOT, admitted, contribution, decisions, state_for, write_state
from scripts.build_knowledge import projection
from scripts.model import Invalid, digest, validate_delta, validate_state
from scripts.verified_admission import plan_verified, verified
from scripts.world_control import plan_admission


class ReportPassageTargetTests(unittest.TestCase):
    def setUp(self):
        self.parent = contribution('simulation')
        self.parent['result']['limitations'] = ['Synthetic original limitation.']
        self.correction = contribution('source_material', '2' * 32)
        self.correction.update(
            schema_version='1.3', parent_run_id=self.parent['id'],
            sources=[], evidence=[], claims=[],
            report_passage_target={
                'submission_sha256': digest(self.parent),
                'report_id': 'synthetic-report',
                'passage_id': 'limitation-0',
            },
        )
        self.correction['result']['summary'] = 'Synthetic correction to one limitation.'
        self.correction['handoff']['no_claims_reason'] = 'The correction supplies no replacement claim.'

    def test_closed_correction_preserves_parent_and_is_available_in_provenance(self):
        base = admitted(self.parent)
        parent_path, = state_for(self.parent)
        correction_path, = state_for(self.correction)
        state = base | state_for(self.correction)
        self.correction['method_metadata']['verification'] = {'version': 1}

        self.assertFalse(verified(self.correction))
        with self.assertRaisesRegex(Invalid, 'no report passage target'):
            plan_verified(state, self.correction['id'], ROOT)
        self.assertTrue(verified({key: value for key, value in self.correction.items()
                                  if key != 'report_passage_target'}))

        with self.assertRaisesRegex(Invalid, 'Awaiting admission'):
            validate_state(state, ROOT, require_closure=True)
        changes = plan_admission(state, self.correction['id'], decisions(self.correction), ROOT)
        self.assertEqual(len(changes), 1)
        closure_path, = changes
        self.assertEqual(changes[closure_path]['claim_dispositions'], [])
        state.update(changes)
        validate_state(state, ROOT, require_closure=True)

        records = projection(state)['provenance']
        self.assertEqual(records[parent_path], self.parent)
        self.assertEqual(records[parent_path]['result']['limitations'], ['Synthetic original limitation.'])
        self.assertEqual(records[correction_path]['report_passage_target'],
                         self.correction['report_passage_target'])
        self.assertEqual(records[closure_path]['submission_sha256'], digest(self.correction))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_state(root / 'base', base)
            write_state(root / 'proposed', state)
            validate_delta(root / 'proposed', root / 'base', state)
            (root / 'empty').mkdir()
            with self.assertRaisesRegex(Invalid, 'parent must be closed on the accepted base'):
                validate_delta(root / 'proposed', root / 'empty', state)

    def test_parent_must_be_local_closed_and_match_digest(self):
        with self.assertRaisesRegex(Invalid, 'unknown parent contribution'):
            validate_state(state_for(self.correction), ROOT)
        with self.assertRaisesRegex(Invalid, 'requires a closed parent'):
            validate_state(state_for(self.parent) | state_for(self.correction), ROOT)

        base = admitted(self.parent)
        self.correction['report_passage_target']['submission_sha256'] = '0' * 64
        with self.assertRaisesRegex(Invalid, 'digest differs from the parent closure'):
            validate_state(base | state_for(self.correction), ROOT)

    def test_target_is_optional_and_requires_one_valid_passage_in_protocol_1_3(self):
        base = admitted(self.parent)
        for version in ('1.0', '1.1', '1.2', '1.3'):
            with self.subTest(legacy_or_unannotated=version):
                correction = self.correction.copy()
                correction['schema_version'] = version
                del correction['report_passage_target']
                validate_state(base | state_for(correction), ROOT)

        for patch in ({
            'schema_version': '1.2',
        }, {
            'parent_run_id': None,
        }, {
            'report_passage_target': [self.correction['report_passage_target']],
        }):
            with self.subTest(patch=patch):
                with self.assertRaises(Invalid):
                    validate_state(base | state_for(self.correction | patch), ROOT)

        for field, value in (('passage_id', ''), ('passage_id', 'first\n'),
                             ('report_id', 'other/report'), ('submission_sha256', 'short')):
            with self.subTest(field=field, value=value):
                correction = copy.deepcopy(self.correction)
                correction['report_passage_target'][field] = value
                with self.assertRaises(Invalid):
                    validate_state(base | state_for(correction), ROOT)
