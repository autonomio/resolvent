"""The nightly brief: a report on one completed recent pass, never knowledge.

The numbers and headings are generated from the completed maintenance record.
The pass writes only the text under "What moved" and "Where the model is going".
Nothing reads a brief as a claim, evidence or canonical record.
"""
from __future__ import annotations

import re
from pathlib import Path

from scripts.model import MAX_FILE_BYTES, Invalid, fail, family
from scripts.temporal import point

ROOT_NAME = 'nightly-briefs'
PATH = re.compile(r'nightly-briefs/([0-9]{4}-[0-9]{2}-[0-9]{2})\.md')
SECTIONS = ('what_moved', 'course')
CITED = re.compile(r'(?<![0-9A-Za-z_-])((?:RUN|BR|BC|[CESRQM])-[0-9a-f]{8,})(?![0-9A-Za-z_])')
COMPLETE = re.compile(r'(?:RUN|BR|BC|[CESRQM])-[0-9a-f]{32}')
CLAIM = re.compile(r'(?<![0-9A-Za-z_-])C-[0-9a-f]{32}(?![0-9A-Za-z_])')
TOP_HEADING = re.compile(r' {0,3}#{1,2}(?:[ \t]|$)')
HEADING = re.compile(r' {0,3}#{1,6}(?:[ \t]|$)')
LIST_ITEM = re.compile(r'[ \t]*(?:[-*+]|[0-9]+[.)])[ \t]')


def recent_pass(record: dict) -> bool:
    return record.get('status') == 'completed' and 'window' in record


def brief_date(record: dict) -> str:
    try:
        kind, instant = point(record['created_at'])
    except (ValueError, TypeError) as error:
        raise Invalid('A recent workset needs a timestamped created_at') from error
    fail(kind == 'instant', 'A recent workset needs a timestamped created_at')
    return instant.date().isoformat()


def brief_path(record: dict) -> str:
    return f'{ROOT_NAME}/{brief_date(record)}.md'


def numbers(record: dict) -> list[tuple[str, int]]:
    """Counts generated from the record's own window and recorded operations."""
    added, ops, window = set(record['claim_ids']), record.get('model_operations', []), record['window']
    merged = {subject for op in ops if op['kind'] == 'comparison' and op['outcome'] == 'equivalent'
              for subject in op['subject_ids'] if subject in added}
    grades = {subject for op in ops if op['kind'] == 'reassessment'
              for subject in op['subject_ids'] if op['uncertainty'] != op['previous_uncertainty'][subject]}
    return [('Claims added', len(added)), ('Claims merged', len(merged)),
            ('Connections added', sum(op['kind'] == 'linkage' and op['previous_sha256'] is None for op in ops)),
            ('Grades changed', len(grades)), ('Questions touched', len(window['question_ids'])),
            ('New sources', len(window['new_source_ids']))]


def render(record: dict, texts: dict) -> str:
    window = record['window']
    start = (f"`{window['from_revision']}` (committed {window['from_committed_at']})"
             if window['from_revision'] else 'the empty model')
    lines = [f'# Nightly brief {brief_date(record)}', '',
             f"Generated from maintenance record {record['id']} and its delta. The pass wrote only the text under "
             '"What moved" and "Where the model is going". This is a report, not knowledge.', '',
             f"- Window: from {start} to `{record['base_commit']}` (committed {window['to_committed_at']})"]
    lines += [f'- {name}: {value}' for name, value in numbers(record)]
    lines += ['', '## What moved', '', texts['what_moved'], '', '## Where the model is going', '', texts['course'], '']
    return '\n'.join(lines)


def written(text: str) -> dict:
    """The pass's own text, located by the two generated section headings."""
    _, found, rest = text.partition('\n## What moved\n\n')
    moved, also, course = rest.partition('\n\n## Where the model is going\n\n')
    fail(bool(found and also), 'Nightly brief lacks its generated sections')
    return {'what_moved': moved, 'course': course[:-1] if course.endswith('\n') else course}


def statements(markdown: str) -> list[str]:
    """Paragraphs and list items; headings are not statements."""
    items, current = [], []
    for line in markdown.split('\n'):
        if not line.strip() or HEADING.match(line):
            if current:
                items.append(' '.join(current))
            current = []
            continue
        if current and LIST_ITEM.match(line):
            items.append(' '.join(current))
            current = []
        current.append(line.strip())
    if current:
        items.append(' '.join(current))
    return items


def check_texts(texts: dict, known: set[str]) -> None:
    fail(isinstance(texts, dict) and set(texts) == set(SECTIONS) and all(isinstance(v, str) for v in texts.values()),
         'A recent pass supplies nightly_brief text for what_moved and course')
    for name in SECTIONS:
        value = texts[name]
        fail(bool(value.strip()) and value == value.strip() and '\r' not in value,
             f'Nightly brief {name} needs trimmed, non-empty text')
        fail(not any(TOP_HEADING.match(line) for line in value.split('\n')),
             'Use level-three headings or lower inside a nightly brief section')
        for cited in CITED.findall(value):
            fail(COMPLETE.fullmatch(cited) is not None, 'Cite complete record IDs in a nightly brief: ' + cited)
            fail(cited in known, 'Nightly brief cites an unknown record: ' + cited)
    for statement in statements(texts['what_moved']):
        fail(CLAIM.search(statement) is not None, 'Every statement in What moved cites a claim ID: ' + statement[:80])


def verify(record: dict, text: str, known: set[str]) -> None:
    """The gate: generated parts exactly as recorded, written parts cite only existing records."""
    texts = written(text)
    check_texts(texts, known)
    fail(render(record, texts) == text, f"Nightly brief numbers or headings differ from {record['id']} and its delta")


def load_briefs(root: Path) -> dict[str, str]:
    folder = root / ROOT_NAME
    if folder.is_symlink():
        raise Invalid('Nightly brief directory cannot be a symlink')
    if not folder.exists():
        return {}
    briefs = {}
    for path in sorted(folder.rglob('*')):
        relative = path.relative_to(root).as_posix()
        fail(not path.is_symlink(), 'Symlink in nightly briefs: ' + relative)
        if not path.is_file() or relative in (ROOT_NAME + '/.gitkeep', ROOT_NAME + '/README.md'):
            continue
        fail(PATH.fullmatch(relative) is not None, 'Unsupported nightly brief file: ' + relative)
        fail(path.stat().st_size <= MAX_FILE_BYTES, 'Nightly brief exceeds the 10 MiB file limit: ' + relative)
        try:
            briefs[relative] = path.read_bytes().decode('utf-8').replace('\r\n', '\n')
        except UnicodeError as error:
            raise Invalid('Nightly brief is not UTF-8: ' + relative) from error
    return briefs


def validate_briefs(state: dict[str, dict], briefs: dict[str, str]) -> None:
    """Each completed recent pass has exactly its brief, and every brief has its pass."""
    passes = {}
    for path, record in sorted(state.items()):
        if family(path) == 'maintenance' and recent_pass(record):
            location = brief_path(record)
            fail(location not in passes, 'Two completed recent passes share the nightly brief ' + location)
            passes[location] = record
    fail(set(briefs) <= set(passes), 'A nightly brief belongs to a completed recent pass: ' +
         ', '.join(sorted(set(briefs) - set(passes))))
    fail(set(passes) <= set(briefs), 'Completed recent pass lacks its nightly brief: ' +
         ', '.join(sorted(set(passes) - set(briefs))))
    known = {record['id'] for record in state.values()}
    for location, record in passes.items():
        verify(record, briefs[location], known)
