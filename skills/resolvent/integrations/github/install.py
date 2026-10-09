#!/usr/bin/env python3
"""Copy the disabled Resolvent observer integration into a local Git checkout.

Python 3.11+; standard library only. No GitHub calls, commits, secret setup, or
workflow activation. Existing files must match; existing instructions are appended.
"""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BUNDLE_ROOT = HERE.parents[1]
MARKER = b'<!-- resolvent-followup:1.3.0 -->'
AGENTS_NOTE = b'''<!-- resolvent-followup:1.3.0 -->
## Resolvent contribution PRs

For Resolvent contribution tasks, read `.github/resolvent/ADMISSION.md`,
`.github/resolvent/PR_FOLLOWUP.md`, `.github/resolvent/CONTINUATION.md`,
`.github/resolvent/MERGE.md`, `.github/resolvent/TARGET.md`, and the approved base contracts.
The originating task owns research context, admission, canonical materialization,
full-delta validation, CI, independent external review, and every correction.
Under the applicable user authorization, it performs the ordinary merge after
fresh readiness checks and verifies MERGED. READY_FOR_MERGE is intermediate.
The optional integration defaults to authoring_owner=originating_task: it only
observes and cannot author, merge, resume the session, or launch a replacement model.
Any host-supported continuation must preserve the originating task's context and
ownership as described in CONTINUATION.md; do not assume such support exists.
Use `.github/resolvent/GITHUB_ACCESS.md` for access and
`.github/resolvent/SUBMISSION.md` for transport retries versus review revisions.
Preserve independent review, repository authority, and the user's merge authority.
<!-- /resolvent-followup:1.3.0 -->
'''
CLAUDE_NOTE = b'''<!-- resolvent-followup:1.3.0 -->
## Resolvent contribution PRs

For Resolvent contribution tasks, read `.github/resolvent/ADMISSION.md`,
`.github/resolvent/PR_FOLLOWUP.md`, `.github/resolvent/CONTINUATION.md`,
`.github/resolvent/MERGE.md`, `.github/resolvent/TARGET.md`, and the repository's
`AGENTS.md` and approved base contracts. The originating task retains context and
owns all work through independent external review, CI, authorized ordinary merge,
and verified MERGED. The optional integration only observes by default; it cannot
author, merge, resume a session, or establish task continuation. This completion
contract applies across providers. Preserve existing instructions and independent review.
<!-- /resolvent-followup:1.3.0 -->
'''


def contained_target(repo, relative):
    target = repo / relative
    for part in (target, *target.parents):
        if part == repo:
            break
        if part.is_symlink():
            raise ValueError('Refusing a symlink in destination: ' + str(part))
        if part != target and part.exists() and not part.is_dir():
            raise ValueError('Destination parent is not a directory: ' + str(part))
    if target.exists() and not target.is_file():
        raise ValueError('Expected a regular destination file: ' + str(target))
    if not target.resolve().is_relative_to(repo):
        raise ValueError('Destination escapes the selected repository')
    return target


def source_files():
    result = {}
    overlay = HERE / 'overlay'
    for path in sorted(overlay.rglob('*')):
        relative = path.relative_to(overlay)
        if '__pycache__' in relative.parts or path.suffix == '.pyc':
            continue
        if path.is_symlink():
            raise ValueError('Refusing a symlink in integration source: ' + str(path))
        if path.is_file():
            result[relative] = path.read_bytes()
    for name in ('PR_FOLLOWUP.md', 'GITHUB_ACCESS.md', 'SUBMISSION.md', 'ADMISSION.md', 'MERGE.md', 'CONTINUATION.md', 'TARGET.md'):
        source = BUNDLE_ROOT / 'references' / name
        if source.is_symlink() or not source.is_file():
            raise ValueError('Missing regular shared reference: ' + str(source))
        result[Path('.github/resolvent') / name] = source.read_bytes()
    if Path('.github/resolvent/controller.py') not in result:
        raise ValueError('Incomplete integration overlay')
    return result


def prepare(repo):
    if not repo.is_dir() or not (repo / '.git').exists():
        raise ValueError('Select the root of an existing local Git checkout')
    operations = []
    for relative, content in source_files().items():
        target = contained_target(repo, relative)
        if target.exists():
            if target.read_bytes() != content:
                raise ValueError('Existing file differs; review an update manually: ' + str(relative))
            operations.append(('unchanged', target, content, None))
        else:
            operations.append(('create', target, content, None))
    for name, note in (('AGENTS.md', AGENTS_NOTE), ('CLAUDE.md', CLAUDE_NOTE)):
        target = contained_target(repo, Path(name))
        before = target.read_bytes() if target.exists() else None
        if before is not None:
            before.decode('utf-8')
            if b'<!-- resolvent-followup:' in before and MARKER not in before:
                raise ValueError('Existing Resolvent instruction block is another version; review the update manually: ' + name)
            if MARKER in before:
                if note not in before:
                    raise ValueError('Existing Resolvent instruction block differs: ' + name)
                operations.append(('unchanged', target, before, before))
                continue
            separator = b'\n' if before.endswith(b'\n') else b'\n\n'
            after = before + (separator if before else b'') + note
            operations.append(('append', target, after, before))
        else:
            operations.append(('create', target, note, None))
    return operations


def install(repo, dry_run=False):
    repo = Path(repo).expanduser().resolve()
    operations = prepare(repo)  # Validate every conflict before making any write.
    for action, target, content, before in operations:
        if not dry_run and action != 'unchanged':
            target.parent.mkdir(parents=True, exist_ok=True)
            if action == 'create':
                with target.open('xb') as handle:
                    handle.write(content)
            else:
                if target.read_bytes() != before:
                    raise ValueError('Instructions changed concurrently: ' + str(target))
                # Append only: retain every original byte, including CRLF or BOM.
                with target.open('ab') as handle:
                    handle.write(content[len(before):])
        print(('would ' if dry_run and action != 'unchanged' else '') + action + ': ' + str(target.relative_to(repo)))
    print('Preview complete.' if dry_run else 'Files prepared. Review and commit them through the repository\'s normal process.')
    print('The integration is disabled until repository policy, environments, credentials, and enrollment are configured. No GitHub action was taken.')
    return operations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', help='Root of an existing local Git checkout')
    parser.add_argument('--dry-run', action='store_true', help='List proposed changes without writing')
    args = parser.parse_args()
    try:
        install(args.repository, args.dry_run)
    except (OSError, UnicodeError, ValueError) as error:
        print('Installation stopped: ' + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
