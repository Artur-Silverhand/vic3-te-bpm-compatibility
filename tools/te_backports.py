"""Reviewed, immutable TE fixes on top of the pinned parent, without rebasing it."""
import hashlib
import json
from pathlib import Path
import re

DIRECTORY='backports/te-2026-11-08'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def apply_unified(text,patch):
    """Apply GitHub's per-file patch only when every old line matches exactly."""
    original=text.splitlines();result=[];cursor=0;lines=patch.splitlines();i=0
    while i<len(lines):
        match=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',lines[i])
        if not match:raise ValueError('Expected unified hunk header')
        start=int(match[1])-1;old_count=int(match[2] or 1);new_count=int(match[4] or 1)
        i+=1;old=[];new=[]
        while i<len(lines) and not lines[i].startswith('@@ '):
            line=lines[i];i+=1
            if line.startswith('\\ No newline'):continue
            if not line or line[0] not in ' +-':raise ValueError('Invalid unified hunk line')
            if line[0] in ' -':old.append(line[1:])
            if line[0] in ' +':new.append(line[1:])
        if len(old)!=old_count or len(new)!=new_count:raise ValueError('Truncated unified patch')
        if start<cursor or original[start:start+old_count]!=old:raise ValueError('Backport hunk no longer matches')
        result.extend(original[cursor:start]);result.extend(new);cursor=start+old_count
    result.extend(original[cursor:]);return '\n'.join(result)+('\n' if text.endswith('\n') else '')


def load(root,parent):
    directory=Path(root)/DIRECTORY;manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    result={}
    for relative,record in manifest['files'].items():
        source=Path(parent)/relative;artifact=directory/'files'/relative
        if not source.resolve().is_relative_to(Path(parent).resolve()) or not artifact.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Unsafe backport path')
        if sha(source)!=record['base_sha256']:raise ValueError('TE backport requires review for changed parent: '+relative)
        if sha(artifact)!=record['sha256']:raise ValueError('TE backport artifact changed: '+relative)
        result[relative]=artifact.read_text(encoding='utf-8-sig')
    return result,{'commits':manifest['commits'],'files':len(result),'scope':manifest['scope']}
