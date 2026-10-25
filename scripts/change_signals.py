#!/usr/bin/env python3
"""Plan a bounded pending workset from an untrusted signal; never research or edit claims."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

import yaml

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.build_knowledge import ROOT, json_bytes
from scripts.change_impact import compare_revisions, explanation_paths, impact_graph
from scripts.model import DATA_ROOTS, Invalid, digest, indexes, load_state, read_data, validate_state
from scripts.signal_contract import metadata_instant, signal_id, validate_signal


def head(root: Path):
    return subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()


def timestamp(value):
    return metadata_instant(value)


def workset_id(revision, sid):
    return 'M-'+uuid.uuid5(uuid.NAMESPACE_URL,'resolvent:'+revision+':'+sid).hex


def plan(root: Path, signal: dict, *, limit=40, debounce_seconds=3600,
         remote_pending=False, now=None):
    validate_signal(signal, ROOT)
    signal = json.loads(json.dumps(signal))  # Normalize value data, never Python object aliases.
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('Signal workset limit must be 1..200')
    if type(debounce_seconds) is not int or not 0 <= debounce_seconds <= 604800:
        raise ValueError('Debounce must be 0..604800 seconds')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Planning time needs an explicit timezone')
    sid = signal_id(signal)
    state = load_state(root)
    idx = indexes(state)
    records = {group:idx.get(group,{}) for group in ('claims','evidence','sources','graph','questions')}
    maintenance = idx.get('maintenance',{})
    result = {'format_version':'1.0','signal_id':sid,'status':None,'workset':None,
              'candidate_total':0,'candidate_claim_ids':[], 'deferred_total':0,'deferred_claim_ids':[]}

    def outcome(status, **fields):
        return dict(result,status=status,**fields)

    prior = [m['id'] for m in maintenance.values() if m.get('trigger',{}).get('signal_id')==sid]
    if prior:
        return outcome('duplicate',existing_workset_ids=sorted(prior))
    if remote_pending or any(m['status']=='pending' for m in maintenance.values()):
        return outcome('deferred_pending_workset',backstop='existing scheduled maintenance; no parallel workset created')
    validate_state(state, ROOT, require_closure=True)
    dirty = subprocess.check_output(['git','-C',str(root),'status','--porcelain','--',*DATA_ROOTS],text=True)
    if dirty.strip():
        raise Invalid('Commit the selected world data before planning an event workset')
    revision = head(root)
    result['base_revision'] = revision
    result['input_state_sha256'] = digest(state)
    if signal['event_type']=='model_changed' and signal['revision']!=revision:
        return outcome('deferred_stale_revision',backstop='existing scheduled maintenance; event is not the selected head')
    recent = [timestamp(m['created_at']) for m in maintenance.values() if m.get('trigger')]
    if recent and now < max(recent)+timedelta(seconds=debounce_seconds):
        return outcome('deferred_debounce',retry_after=(max(recent)+timedelta(seconds=debounce_seconds)).isoformat(),
                       backstop='existing scheduled maintenance remains enabled')

    reasons = {}
    def candidate(cid, reason):
        if cid in records['claims']:
            reasons.setdefault(cid,set()).add(reason)
    seeds = set(signal['affected_ids'])
    unknown = sorted(seeds-set().union(*(set(group) for group in records.values()),set(maintenance)))
    if signal['event_type']=='model_changed':
        try:
            impact = compare_revisions(root,signal['before_revision'],signal['revision'])
        except (Invalid, OSError, subprocess.CalledProcessError):
            return outcome('deferred_unavailable_revision',backstop='existing scheduled maintenance; no source was fetched')
        for change in impact['changes']:
            seeds.add(change['id'])
            if change['group']=='claims':
                candidate(change['id'],'changed_claim')
        for category in ('dependency_impacts','contextual_impacts'):
            for item in impact[category]:
                candidate(item['claim_id'],category)
        result['impact_revisions'] = {'before':impact['before']['source_revision'],'after':impact['after']['source_revision']}

    # Source reuse is declared metadata. It expands advisory discovery, not truth.
    for source in records['sources'].values():
        parents, pending = set(), list(source.get('ancestry',{}).get('parent_source_ids',[]))
        while pending:
            parent = pending.pop()
            if parent not in parents:
                parents.add(parent)
                pending.extend(records['sources'][parent].get('ancestry',{}).get('parent_source_ids',[]))
        if parents.intersection(seeds):
            seeds.add(source['id'])
    hard, contextual = impact_graph(records)
    for seed in sorted(seeds):
        candidate(seed,'declared_or_changed_claim')
        if seed in maintenance:
            for cid in maintenance[seed]['claim_ids']:
                candidate(cid,'declared_workset_reference')
        if seed in records['questions']:
            for cid in records['questions'][seed]['claim_ids']:
                candidate(cid,'declared_question_reference')
        for category, paths in zip(('dependency_impacts','contextual_impacts'),explanation_paths(seed,records,hard,contextual)):
            for cid in paths:
                candidate(cid,category)
    gap_claims = {cid for question in records['questions'].values() for cid in question['claim_ids']}
    for closure in idx.get('closure',{}).values():
        if closure['follow_up_gaps']:
            gap_claims.update(d['claim_id'] for d in closure['claim_dispositions'] if d['claim_id'])
    ranked = sorted(reasons,key=lambda cid:(
        'changed_claim' not in reasons[cid] and 'declared_or_changed_claim' not in reasons[cid],
        'dependency_impacts' not in reasons[cid],cid not in gap_claims,cid))
    selected, deferred = ranked[:limit],ranked[limit:]
    result.update(candidate_total=len(ranked),candidate_claim_ids=ranked[:200],
                  deferred_total=len(deferred),deferred_claim_ids=deferred[:200],unknown_affected_ids=unknown)
    if not selected:
        return outcome('deferred_no_known_claims',backstop='signal grants no authority for unbounded research')
    mid = workset_id(revision,sid)
    notes = ['Change signal only; no external source was fetched, relationship justified or truth status changed.']
    notes += [cid+': '+', '.join(sorted(reasons[cid]))+('; recorded prior question/follow-up gap' if cid in gap_claims else '')
              for cid in selected]
    workset = {'schema_version':'1.1','id':mid,'status':'pending','base_commit':revision,
               'created_at':now.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),
               'claim_ids':selected,'reviewed_claim_ids':[],'touched_files':[], 'findings':notes,
               'deferred':(['Bounded selection deferred '+str(len(deferred))+' additional candidates: '+', '.join(deferred[:200])]
                           if deferred else []) +
                          (['Unknown affected IDs were not researched: '+', '.join(unknown)] if unknown else []),
               'no_change_reason':None,
               'trigger':{'signal_id':sid,'signal':copy.deepcopy(signal)}}
    proposed = dict(state)
    proposed['maintenance/'+mid+'.yaml'] = workset
    validate_state(proposed, ROOT, require_closure=False)
    return outcome('planned',workset=workset,**{key:value for key,value in result.items() if key not in ('status','workset')})


def apply(root: Path, result: dict):
    if result['status']!='planned':
        return None
    if head(root)!=result['base_revision']:
        raise Invalid('Selected repository advanced; replan before writing a workset')
    current = load_state(root)
    relative = 'maintenance/'+result['workset']['id']+'.yaml'
    if relative in current:
        if current[relative]!=result['workset']:
            raise Invalid('An existing workset differs; no overwrite performed')
        current.pop(relative)
    if digest(current)!=result['input_state_sha256']:
        raise Invalid('World data changed after planning; replan before writing a workset')
    folder = root/'maintenance'
    if folder.is_symlink():
        raise Invalid('Maintenance directory cannot be a symlink')
    folder.mkdir(exist_ok=True)
    path = folder/(result['workset']['id']+'.yaml')
    data = yaml.safe_dump(result['workset'],sort_keys=False,allow_unicode=True).encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=root,prefix='.signal-',suffix='.tmp',delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        os.link(temporary,path)  # Atomic create, never overwrite an existing record/symlink.
    except FileExistsError:
        if read_data(path)!=result['workset']:
            raise Invalid('An existing workset differs; no overwrite performed')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('.'))
    parser.add_argument('--signal',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=40)
    parser.add_argument('--debounce-seconds',type=int,default=3600)
    parser.add_argument('--remote-pending',action='store_true')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        result=plan(args.root,read_data(args.signal),limit=args.limit,
                    debounce_seconds=args.debounce_seconds,remote_pending=args.remote_pending)
        if args.apply:
            path=apply(args.root,result)
            if path is not None:
                result['written_path']=path.relative_to(args.root).as_posix()
        sys.stdout.buffer.write(json_bytes(result))
    except (Invalid,ValueError,OSError,subprocess.CalledProcessError) as error:
        parser.exit(1,'Change signal not applied: '+str(error)+'\n')


if __name__=='__main__':
    main()
