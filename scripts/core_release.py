#!/usr/bin/env python3
"""Version an explicit inventory of generic core files, excluding world-model data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from scripts.build_knowledge import json_bytes
from scripts.model import Invalid, unique_pairs

LOCK='resolvent-core.lock.json'
UPSTREAM='https://github.com/autonomio/resolvent.git'
CHANNEL='core-release'
ROOT_FILES={'.gitignore','AGENTS.md','CLAUDE.md','LICENSE','README.md','plugin.json','pyproject.toml','requirements.txt'}
PREFIXES={'.github','.agents','.claude-plugin','.codex-plugin','scripts','tests','docs','skills',
          'workflows','assets','dist','verification'}
MAX_FILES=1000
MAX_TOTAL=32*1024*1024


def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',value):
        raise Invalid('Core version must be a three-part release version')
    return tuple(map(int,value.split('.')))


def core_path(path):
    if not isinstance(path,str) or not re.fullmatch(r'[A-Za-z0-9_.\-/]+',path):
        return False
    parts=PurePosixPath(path).parts
    return (PurePosixPath(path).as_posix()==path and not path.startswith('/') and
            not any(part in ('','.','..','.git') for part in parts) and
            (path in ROOT_FILES or (len(parts)>1 and parts[0] in PREFIXES)))


def git(root,*args,input=None,extra_env=None):
    response=subprocess.run(['git','--no-replace-objects','-C',str(root),*args],input=input,
                            capture_output=True,env={**os.environ,'GIT_NO_LAZY_FETCH':'1',
                            'GIT_TERMINAL_PROMPT':'0',**(extra_env or {})})
    if response.returncode:
        raise Invalid('Git operation failed: '+args[0])
    return response.stdout


def decode(raw):
    if len(raw)>1024*1024:
        raise Invalid('Core metadata exceeds 1 MiB')
    try:
        return json.loads(raw,object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Invalid('Non-finite core metadata')))
    except (ValueError,UnicodeError,RecursionError) as error:
        raise Invalid('Invalid core metadata') from error


def inventory(root,revision):
    files={}
    for entry in git(root,'ls-tree','-r','-z','--full-tree',revision).split(b'\0'):
        if not entry:
            continue
        meta,raw=entry.split(b'\t',1);mode,kind,oid=meta.decode().split();path=raw.decode()
        if not core_path(path):
            continue
        if kind!='blob' or mode not in ('100644','100755'):
            raise Invalid('Managed core files must be regular Git blobs')
        data=git(root,'cat-file','blob',oid)
        files[path]={'mode':mode,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'git_blob':oid}
    return files


def validate_lock(lock):
    if not isinstance(lock,dict) or set(lock)!={'format_version','core_version','files'} or lock['format_version']!='1.0':
        raise Invalid('Unsupported core lock format')
    version(lock['core_version'])
    files=lock['files']
    if not isinstance(files,dict) or not 1<=len(files)<=MAX_FILES:
        raise Invalid('Invalid core inventory bound')
    total=0
    for path,item in files.items():
        if not core_path(path) or not isinstance(item,dict) or set(item)!={'mode','bytes','sha256','git_blob'}:
            raise Invalid('Unsafe or unexpected managed core entry')
        if item['mode'] not in ('100644','100755') or type(item['bytes']) is not int or not 0<=item['bytes']<=8*1024*1024:
            raise Invalid('Invalid managed core file metadata')
        if not isinstance(item['sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',item['sha256']):
            raise Invalid('Invalid core content hash')
        if not isinstance(item['git_blob'],str) or not re.fullmatch(r'[0-9a-f]{40}',item['git_blob']):
            raise Invalid('Invalid core Git blob')
        total+=item['bytes']
    if total>MAX_TOTAL:
        raise Invalid('Core inventory exceeds 32 MiB')
    # A file may not replace an ancestor directory or its child in one inventory.
    if any('/'.join(path.split('/')[:i]) in files for path in files for i in range(1,len(path.split('/')))):
        raise Invalid('Core file/directory collision')
    return lock


def checked_lock(root,revision='HEAD'):
    lock=validate_lock(decode(git(root,'show',revision+':'+LOCK)))
    if lock['files']!=inventory(root,revision):
        raise Invalid('Core lock does not match committed core files; regenerate it and bump the core version')
    return lock


def validate_index(index):
    if (not isinstance(index,dict) or set(index)!={'format_version','core_version','source_commit','lock_sha256'}
            or index['format_version']!='1.0'):
        raise Invalid('Unsupported core release index')
    version(index['core_version'])
    if not isinstance(index['source_commit'],str) or not re.fullmatch(r'[0-9a-f]{40}',index['source_commit']):
        raise Invalid('Core release needs a full immutable source revision')
    if not isinstance(index['lock_sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',index['lock_sha256']):
        raise Invalid('Invalid core lock digest')
    return index


def release_index(root,previous=None):
    lock=checked_lock(root)
    raw=git(root,'show','HEAD:'+LOCK)
    index={'format_version':'1.0','core_version':lock['core_version'],
           'source_commit':git(root,'rev-parse','HEAD').decode().strip(),
           'lock_sha256':hashlib.sha256(raw).hexdigest()}
    if previous is not None:
        validate_index(previous)
        old,new=version(previous['core_version']),version(index['core_version'])
        if new<old or (new==old and previous['lock_sha256']!=index['lock_sha256']):
            raise Invalid('Core channel cannot roll back or replace a version')
        if new==old:
            return previous
    return index


def check_version(root,base):
    current=checked_lock(root)
    present=git(root,'ls-tree','--name-only',base,'--',LOCK).decode().strip()
    if not present:
        return
    old=validate_lock(decode(git(root,'show',base+':'+LOCK)))
    if (version(current['core_version'])<version(old['core_version']) or
            (current['files']!=old['files'] and version(current['core_version'])<=version(old['core_version']))):
        raise Invalid('Changed core files require a higher core version')


def publish_channel(root,repository):
    if repository!='autonomio/resolvent':
        raise Invalid('Only the upstream repository publishes the core channel')
    remote=git(root,'ls-remote','origin','refs/heads/'+CHANNEL).decode().split()
    parent=None;previous=None
    if remote:
        git(root,'fetch','--no-tags','origin','refs/heads/'+CHANNEL)
        parent=git(root,'rev-parse','FETCH_HEAD').decode().strip()
        previous=decode(git(root,'show',parent+':core.json'))
    index=release_index(root,previous)
    if index==previous:
        return {'status':'current','core_version':index['core_version']}
    blob=git(root,'hash-object','-w','--stdin',input=json_bytes(index)).decode().strip()
    with tempfile.TemporaryDirectory() as temporary:
        env={'GIT_INDEX_FILE':str(Path(temporary)/'index')}
        git(root,'read-tree','--empty',extra_env=env)
        git(root,'update-index','-z','--index-info',input=('100644 '+blob+'\tcore.json\0').encode(),extra_env=env)
        tree=git(root,'write-tree',extra_env=env).decode().strip()
    args=['commit-tree',tree]+(['-p',parent] if parent else [])
    commit=git(root,*args,input=('Release Resolvent core '+index['core_version']+'\n').encode(),extra_env={
        'GIT_AUTHOR_NAME':'github-actions[bot]','GIT_COMMITTER_NAME':'github-actions[bot]',
        'GIT_AUTHOR_EMAIL':'41898282+github-actions[bot]@users.noreply.github.com',
        'GIT_COMMITTER_EMAIL':'41898282+github-actions[bot]@users.noreply.github.com'}).decode().strip()
    git(root,'push','origin',commit+':refs/heads/'+CHANNEL)
    return {'status':'published','core_version':index['core_version'],'source_commit':index['source_commit']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('.'))
    commands=parser.add_subparsers(dest='command',required=True)
    lock=commands.add_parser('lock');lock.add_argument('--version',required=True)
    check=commands.add_parser('check');check.add_argument('--base')
    prepare=commands.add_parser('prepare');prepare.add_argument('--previous',type=Path)
    publish=commands.add_parser('publish');publish.add_argument('--repository',required=True)
    args=parser.parse_args()
    try:
        if args.command=='lock':
            version(args.version)
            # Staged files make new source paths explicit; ignored/untracked data is never inventoried.
            files=inventory(args.root,git(args.root,'write-tree').decode().strip())
            result=validate_lock({'format_version':'1.0','core_version':args.version,'files':files})
            if (args.root/LOCK).is_symlink():
                raise Invalid('Core lock cannot be a symlink')
            (args.root/LOCK).write_bytes(json_bytes(result))
        elif args.command=='check':
            checked_lock(args.root)
            if args.base:
                check_version(args.root,args.base)
            print('Committed core inventory is consistent.')
        elif args.command=='prepare':
            previous=decode(args.previous.read_bytes()) if args.previous else None
            sys.stdout.buffer.write(json_bytes(release_index(args.root,previous)))
        else:
            sys.stdout.buffer.write(json_bytes(publish_channel(args.root,args.repository)))
    except (Invalid,ValueError,OSError,KeyError) as error:
        parser.exit(1,'Core release stopped: '+str(error)+'\n')


if __name__=='__main__':
    main()
