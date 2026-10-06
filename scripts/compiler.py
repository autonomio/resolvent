#!/usr/bin/env python3
"""Validate a proposal/world model. Structural success is not epistemic approval."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.model import Invalid, load_state, validate_delta, validate_state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--policy-root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--base', type=Path, help='Trusted base checkout, for PR delta enforcement')
    parser.add_argument('--require-closure', action='store_true', help='Merge gate: all proposals and maintenance must be processed')
    args = parser.parse_args()
    try:
        state = load_state(args.root)
        counts = validate_state(state, args.policy_root, args.require_closure)
        if args.base:
            validate_delta(args.root, args.base, state)
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    print(json.dumps({'structural_validation': 'passed', 'records': counts,
                      'semantic_review': 'required separately; not established by CI'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
