#!/usr/bin/env python3
"""Declared answer spaces and claim answers: exact arithmetic shared by validation and measurement.

A question may declare the finite set of answers it distinguishes; a claim may
declare which of them its statement admits. Nothing here reads a statement or
judges whether a declaration is right.
"""
from __future__ import annotations

from fractions import Fraction
import math
import re

DECIMAL = re.compile(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?')


def number(value) -> Fraction:
    """Decimal text to an exact rational. Binary floats never enter the arithmetic."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Fraction(value)
    if isinstance(value, str) and DECIMAL.fullmatch(value):
        return Fraction(value)
    raise ValueError('Answer numbers must be plain decimal text')


def grid(space: dict) -> tuple[Fraction, Fraction, int]:
    """A numeric space is a finite row of cells; `step` is the precision that matters.

    Cell k is centred on low + k*step, for k from 0 to (high - low)/step. Without
    a step a claim could buy unbounded bits by printing more digits.
    """
    low, high, step = number(space['low']), number(space['high']), number(space['step'])
    if step <= 0 or high <= low:
        raise ValueError('A numeric answer space needs low < high and a positive step')
    count = (high - low) / step
    if count.denominator != 1:
        raise ValueError('A numeric answer space must span a whole number of steps')
    return low, step, int(count) + 1


def capacity(space: dict) -> int:
    """Number of distinguishable answers; log2 of it is the most a question can hold."""
    return len(space['values']) if space['kind'] == 'categorical' else grid(space)[2]


def validate_space(space: dict) -> None:
    if space['kind'] == 'numeric':
        grid(space)


def admitted_set(space: dict, answer: dict):
    """Canonical admitted set: a frozenset of values, or merged half-open ranges of cell indexes."""
    if space['kind'] == 'categorical':
        if 'values' not in answer:
            raise ValueError('An answer to a categorical question lists values')
        values = frozenset(answer['values'])
        if not values or not values <= frozenset(space['values']):
            raise ValueError('Answer values must be a nonempty part of the declared space')
        return values
    if 'ranges' not in answer:
        raise ValueError('An answer to a numeric question lists ranges')
    low, step, count = grid(space)
    merged = []
    for start, end in sorted((number(item['low']), number(item['high'])) for item in answer['ranges']):
        if not start < end:
            raise ValueError('An answer range needs low < high')
        # Every cell the stated range touches: precision finer than the step earns nothing.
        first = math.floor((start - low) / step - Fraction(1, 2)) + 1
        last = math.ceil((end - low) / step + Fraction(1, 2)) - 1
        if first < 0 or last >= count:
            raise ValueError('An answer range must lie inside the declared space')
        if merged and first <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], last + 1))
        else:
            merged.append((first, last + 1))
    return tuple(merged)


def validate_answers(claim: dict, questions: dict) -> None:
    """Structure and references only: one answer per question, inside its space, on the claim's own evidence."""
    seen = set()
    for answer in claim.get('answers', []):
        question_id = answer['question_id']
        if question_id in seen:
            raise ValueError(f'more than one answer to {question_id}')
        seen.add(question_id)
        question = questions.get(question_id)
        if question is None:
            raise ValueError(f'answer to unknown question {question_id}')
        if 'space' not in question:
            raise ValueError(f'{question_id} declares no answer space')
        admitted_set(question['space'], answer)
        if not set(answer['evidence_ids']) <= set(claim['evidence_ids']):
            raise ValueError(f"answer to {question_id} cites evidence that is not the claim's own")

