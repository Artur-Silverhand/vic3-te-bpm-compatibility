"""Update only our installed patch after a fresh synthetic PASS, with backup.

Original TE/BPM, Steam, saves and playsets are never written or launched.
Unknown edits in the installed patch cause a stop before the first write.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid
import re

from build_patch import ROOT,OUTPUT,VERSION,digest
from prepare_local_profile import documents
from source_state import require_fresh_inputs


def files(root):return {p.relative_to(root).as_posix():p for p in root.rglob('*') if p.is_file()}


def update(target,baseline,source,backup):
    target=target.resolve();baseline=baseline.resolve();source=source.resolve();backup=backup.resolve()
    assert target.is_dir() and baseline.is_dir() and source.is_dir()
    assert target not in {baseline,source,backup} and not backup.exists()
    old=files(baseline);installed=files(target);new=files(source)
    assert installed.keys()==old.keys(),'Installed patch file set changed; no files were overwritten'
    assert new.keys()>=old.keys(),'Removed files need a separately reviewed migration'
    for relative,path in installed.items():
        assert path.resolve().is_relative_to(target),'Installed link escapes patch folder'
        assert not path.is_symlink(),'Installed patch contains a symlink'
        assert digest(path)==digest(old[relative]),'Installed patch was edited: '+relative
    metadata=json.loads((source/'.metadata/metadata.json').read_text(encoding='utf-8'))
    previous=json.loads((target/'.metadata/metadata.json').read_text(encoding='utf-8'))
    assert metadata['id']==previous['id']=='44a453ae-01a4-49e4-991c-4f1eaa2ae614'
    shutil.copytree(target,backup)
    expected={relative:path.read_bytes() for relative,path in new.items()}
    metadata['name']='TBCP 3 - Compatibility '+metadata['version']
    expected['.metadata/metadata.json']=(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    written=[]
    try:
        for relative,data in expected.items():
            path=target/relative
            assert path.resolve().is_relative_to(target),'Unsafe generated path'
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_name(path.name+'.tbcp-tmp-'+uuid.uuid4().hex)
            try:
                temp.write_bytes(data);temp.replace(path)
            finally:
                if temp.exists():temp.unlink()
            written.append(relative)
        for relative,data in expected.items():
            assert hashlib.sha256((target/relative).read_bytes()).digest()==hashlib.sha256(data).digest(),relative
    except Exception:
        # Restore only known owned files; never recursively delete a directory.
        for relative,path in old.items():
            destination=target/relative
            assert destination.resolve().is_relative_to(target)
            shutil.copy2(backup/relative,destination)
        for relative in set(written)-old.keys():
            path=target/relative
            assert path.resolve().is_relative_to(target)
            path.unlink(missing_ok=True)
        raise
    return {'path':str(target),'backup':str(backup),'version':metadata['version'],'file_count':len(new),
            'name':metadata['name'],'game_launched':False,'playset_changed':False}


def install():
    gate=json.loads((ROOT/'docs/validation/synthetic-gate.json').read_text(encoding='utf-8'))
    assert gate['status']=='PASS' and gate['version']==VERSION
    assert gate['patch_sha256']=={rel:digest(p) for rel,p in files(OUTPUT).items()},'Build changed after gate'
    assert gate['tools_sha256']=={p.relative_to(ROOT).as_posix():digest(p) for p in sorted((ROOT/'tools').glob('*')) if p.suffix in {'.py','.ps1'}},'Tools changed after gate'
    require_fresh_inputs(gate,ROOT)
    profile_path=ROOT/'docs/validation/installed-profile.json'
    profile=json.loads(profile_path.read_text(encoding='utf-8'))
    required={label:gate['source_state']['sources'][label]['commit'] for label in ('timeline','bpm')}
    assert profile['source_commits']==required,'Installed parent mods differ; prepare a complete new profile'
    target=Path(profile['packages']['patch']['path']).resolve()
    mod_root=(documents()/'Paradox Interactive/Victoria 3/mod').resolve()
    assert target.parent==mod_root and re.fullmatch(r'tbcp_patch_(?:040dev|\d+\.\d+\.\d+(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?)',target.name),'Unexpected installation target'
    baseline=Path(profile['packages']['patch'].get('baseline_snapshot',str(ROOT/'runtime/local-mods/tbcp_patch_040dev')))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    backup=ROOT/'runtime/backups'/('installed-patch-before-'+VERSION+'-'+stamp)
    assert backup.resolve().is_relative_to((ROOT/'runtime/backups').resolve())
    result=update(target,baseline,OUTPUT,backup)
    snapshot=ROOT/'runtime/installed-snapshots'/(VERSION+'-'+stamp)
    shutil.copytree(target,snapshot)
    profile['version']=VERSION;profile['patch_update']=result
    profile['packages']['patch'].update({k:result[k] for k in ['file_count','name']})
    profile['packages']['patch']['baseline_snapshot']=str(snapshot)
    profile_path.write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'docs/validation/installed-patch-update.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':install()
