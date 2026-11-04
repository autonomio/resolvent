#!/usr/bin/env python3
"""Prepare a bounded maintenance workset; never invent connections or change claims."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.model import DATA_ROOTS, Invalid, indexes, load_state


def recent_workset(root: Path, hours: int = 24, now: datetime | None = None) -> dict | None:
    """Exactly the claims added in the recent window; nothing added means no workset."""
    from scripts.recent_additions import WINDOW_FIELDS, recorded_ids, window
    if subprocess.check_output(['git','-C',str(root),'status','--porcelain','--',*DATA_ROOTS],text=True).strip():
        raise Invalid('Commit the world data before preparing a recent workset')
    idx = indexes(load_state(root))
    span = window(root, 'HEAD', idx.get('maintenance', {}).values(), hours=hours, at=now)
    before = recorded_ids(root, span['from_revision'])
    added = sorted(cid for cid in idx.get('claims', {}) if cid not in before)
    if not added:
        return None
    return {'schema_version':'1.3','id':'M-'+uuid.uuid4().hex,'status':'pending','base_commit':span['to_revision'],
            'created_at':span['at'],'claim_ids':added,'reviewed_claim_ids':[],'touched_files':[], 'findings':[],
            'deferred':[], 'no_change_reason':None, 'window':{key: span[key] for key in WINDOW_FIELDS}}


def workset(root: Path, limit: int = 40) -> dict | None:
    if limit < 2:
        raise ValueError('Maintenance workset limit must be at least 2')
    idx = indexes(load_state(root))
    claims = idx.get('claims', {})
    active = sorted(cid for cid, c in claims.items() if c['state'] == 'active')
    if not active:
        return None
    reviewed = set()
    for record in idx.get('maintenance', {}).values():
        if record['status'] == 'completed':
            reviewed.update(record['reviewed_claim_ids'])
    never_reviewed = [cid for cid in active if cid not in reviewed]
    # Half prioritizes never-reviewed claims, half rotates through the entire model.
    # This reaches disconnected old regions instead of only following existing edges.
    # Targeted and recent worksets count as coverage but do not advance the rotation.
    completed_runs = sum(1 for record in idx.get('maintenance', {}).values()
                         if record['status'] == 'completed' and not record.get('trigger') and 'window' not in record)
    start = (completed_runs * max(1, limit // 2)) % len(active)
    rotating = active[start:] + active[:start]
    selected = list(dict.fromkeys(never_reviewed[:limit // 2] + rotating[:limit // 2]))
    selected += [cid for cid in rotating if cid not in selected][:max(0, limit-len(selected))]
    commit = subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'], text=True).strip()
    return {'schema_version':'1.0','id':'M-'+uuid.uuid4().hex,'status':'pending','base_commit':commit,
            'created_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
            'claim_ids':selected,'reviewed_claim_ids':[],'touched_files':[], 'findings':[], 'deferred':[], 'no_change_reason':None}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('.'))
    parser.add_argument('--limit',type=int,default=40)
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--recent',action='store_true',help='Select exactly the claims added in the recent window')
    parser.add_argument('--hours',type=int,default=24,help='Recent window when no recent workset has completed')
    args=parser.parse_args()
    result=recent_workset(args.root,args.hours) if args.recent else workset(args.root,args.limit)
    if result is None:
        print('No claims were added in the recent window: no maintenance PR needed.' if args.recent
              else 'Empty world model: no maintenance PR needed.')
    elif args.write:
        p=args.root/'maintenance'/f"{result['id']}.yaml"
        p.parent.mkdir(exist_ok=True)
        p.write_text(yaml.safe_dump(result, sort_keys=False))
        print(p.as_posix())
    else:
        print(json.dumps(result,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
