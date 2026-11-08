"""Install the two verified localization archives as new local mods."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import sys
import zipfile

from loclib import ROOT,json_write
from maintain import PACKS,OUTPUT,audit


def install(apply=False):
    if not audit(argparse.Namespace(te_localization=None,bpm_localization=None)):
        raise ValueError('Translation inputs changed')
    sys.path.insert(0,str(ROOT/'tools'))
    from prepare_local_profile import documents
    mod_root=(documents()/'Paradox Interactive/Victoria 3/mod').resolve()
    report=json.loads((OUTPUT/'package-report.json').read_text(encoding='utf-8'));plan=[]
    for pack,config in PACKS.items():
        target=(mod_root/config['slug']).resolve()
        if target.parent!=mod_root:raise ValueError('Unexpected installation target')
        archive=ROOT/'dist'/report[pack]['archive']
        if archive.parent.resolve()!=(ROOT/'dist').resolve():raise ValueError('Unsafe archive path')
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=report[pack]['sha256']:raise ValueError('Archive changed')
        with zipfile.ZipFile(archive) as saved:
            contents={name:saved.read(name) for name in saved.namelist()}
        for name in contents:
            path=PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe archive member')
        metadata=json.loads(contents['.metadata/metadata.json'])
        if metadata['id']!=config['id']:raise ValueError('Unexpected mod identity')
        if target.exists():
            actual={path.relative_to(target).as_posix():path.read_bytes() for path in target.rglob('*') if path.is_file()}
            if actual!=contents:raise ValueError('Existing installation differs; no files overwritten: '+target.name)
        plan.append((target,contents,metadata))
    # Validate both targets before the first write; never edit Workshop originals.
    result=[]
    for target,contents,metadata in plan:
        if apply and not target.exists():
            target.mkdir(parents=True)
            for name,data in contents.items():
                path=target/name
                if not path.resolve().is_relative_to(target):raise ValueError('Unsafe installed path')
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        if apply:
            for name,data in contents.items():
                if (target/name).read_bytes()!=data:raise ValueError('Installation verification failed')
        result.append({'name':metadata['name'],'version':metadata['version'],'path':str(target),'files':len(contents)})
    json_write(ROOT/'runtime/translations/installed.json',{'applied':apply,'mods':result,'game_launched':False,'playset_changed':False})
    print(json.dumps({'applied':apply,'mods':result},ensure_ascii=True,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true')
    install(parser.parse_args().apply)
