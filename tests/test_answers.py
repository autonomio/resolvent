"""Declared answer spaces and answers: what the compiler accepts, and that undeclared records stay valid."""
from __future__ import annotations

import copy
import unittest

from scripts.answers import admitted_set, capacity, number
from scripts.build_knowledge import ROOT, projection
from scripts.information import ledger
from scripts.model import Invalid, validate_state
from test_model import admitted, contribution

YES_NO = {'kind': 'categorical', 'values': ['yes', 'no']}
VALUE = {'kind': 'numeric', 'low': '0', 'high': '10', 'step': '0.5', 'unit': 'synthetic units'}


def declared(space=None, answer=None, focus=None) -> tuple[dict, dict, dict]:
    """An admitted synthetic claim and question, annotated the way reviewed maintenance would."""
    proposal = contribution()
    proposal['questions'] = [{'id': 'q1', 'question': 'What is the synthetic value?', 'claim_ids': ['c1']}]
    state = admitted(proposal)
    claim = next(record for path, record in state.items() if path.startswith('claims/'))
    question = next(record for path, record in state.items() if path.startswith('questions/'))
    if space is not None:
        question['space'] = copy.deepcopy(space)
    if focus is not None:
        question['focus'] = focus
    if answer is not None:
        claim['answers'] = [{'question_id': question['id'], 'evidence_ids': list(claim['evidence_ids']), **copy.deepcopy(answer)}]
    return state, claim, question


class Declarations(unittest.TestCase):
    def rejected(self, pattern: str, **kwargs):
        mutate = kwargs.pop('mutate', None)
        state, claim, question = declared(**kwargs)
        if mutate:
            mutate(claim, question)
        with self.assertRaisesRegex(Invalid, pattern):
            validate_state(state, ROOT, True)

    def test_undeclared_records_are_unchanged_and_valid(self):
        state, claim, question = declared()
        self.assertNotIn('answers', claim)
        self.assertNotIn('space', question)
        self.assertEqual(validate_state(state, ROOT, True)['questions'], 1)

    def test_declared_space_and_answer_validate_and_are_measured(self):
        state, claim, question = declared(VALUE, {'ranges': [{'low': '6.75', 'high': '7.25'}]}, focus=True)
        validate_state(state, ROOT, True)
        records = projection(state)['records']
        self.assertEqual(records['claims'][claim['id']]['answers'], claim['answers'])  # native fields are preserved
        report = ledger(records)['commitment']
        self.assertEqual(report['by_question'][question['id']]['held']['ratio'], '21/1')  # one cell of 21
        self.assertEqual((report['held_on_focus']['ratio'], report['claims_answering']), ('21/1', 1))
        state, _, _ = declared(YES_NO, {'values': ['yes']})
        validate_state(state, ROOT, True)

    def test_a_space_without_an_answer_and_a_focus_without_a_space_are_valid(self):
        validate_state(declared(YES_NO)[0], ROOT, True)
        validate_state(declared(focus=True)[0], ROOT, True)

    def test_numeric_space_needs_a_step_and_a_whole_number_of_cells(self):
        self.rejected('is not valid under any of the given schemas', space={'kind': 'numeric', 'low': '0', 'high': '10'})
        self.rejected('whole number of steps', space={**VALUE, 'step': '3'})
        self.rejected('positive step', space={**VALUE, 'step': '0'})
        self.rejected('low < high', space={**VALUE, 'low': '10'})
        self.rejected('is not valid under any of the given schemas', space={**VALUE, 'step': 0.5})  # binary float
        self.rejected('is not valid under any of the given schemas', space={'kind': 'categorical', 'values': ['only']})

    def test_answer_must_fit_its_question(self):
        self.rejected('declares no answer space', answer={'values': ['yes']})
        self.rejected('nonempty part of the declared space', space=YES_NO, answer={'values': ['maybe']})
        self.rejected('lists values', space=YES_NO, answer={'ranges': [{'low': '1', 'high': '2'}]})
        self.rejected('lists ranges', space=VALUE, answer={'values': ['yes']})
        self.rejected('inside the declared space', space=VALUE, answer={'ranges': [{'low': '9', 'high': '12'}]})
        self.rejected('low < high', space=VALUE, answer={'ranges': [{'low': '7', 'high': '7'}]})
        self.rejected('does not match', space=VALUE, answer={'ranges': [{'low': '7e0', 'high': '8'}]})
        self.rejected('is not valid under any of the given schemas|valid under each of', space=YES_NO,
                      answer={'values': ['yes'], 'ranges': [{'low': '1', 'high': '2'}]})

    def test_answer_references_are_checked(self):
        self.rejected('unknown question', space=YES_NO, answer={'values': ['yes']},
                      mutate=lambda claim, question: claim['answers'][0].update(question_id='Q-' + 'f' * 32))
        self.rejected("not the claim's own", space=YES_NO, answer={'values': ['yes']},
                      mutate=lambda claim, question: claim['answers'][0].update(evidence_ids=['E-' + 'f' * 32]))
        self.rejected('more than one answer', space=YES_NO, answer={'values': ['yes']},
                      mutate=lambda claim, question: claim['answers'].append(copy.deepcopy(claim['answers'][0])))

    def test_cells_are_centred_and_ranges_admit_every_cell_they_touch(self):
        self.assertEqual(capacity(VALUE), 21)
        self.assertEqual(admitted_set(VALUE, {'ranges': [{'low': '6.75', 'high': '7.25'}]}), ((14, 15),))
        self.assertEqual(admitted_set(VALUE, {'ranges': [{'low': '6.9', 'high': '8.1'}]}), ((14, 17),))
        self.assertEqual(admitted_set(VALUE, {'ranges': [{'low': '1', 'high': '2'}, {'low': '1.5', 'high': '3'}]}), ((2, 7),))
        with self.assertRaises(ValueError):
            number(0.1)


if __name__ == '__main__':
    unittest.main()
