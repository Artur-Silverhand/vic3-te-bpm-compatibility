"""Copy three isolated local mods. Does not launch Steam, game or change a playset.

Default destination is inside this workspace. --install copies to the Windows
Known Folder Documents/Paradox Interactive/Victoria 3/mod instead. Existing
destination folders cause a stop; no folder is deleted or overwritten.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid

from build_patch import ROOT, OUTPUT, VERSION
from source_state import load_lock,source_state

RUNTIME_DIRECTORIES={'.metadata','common','events','gui','gfx','localization','map_data',
                     'dlc','dlc_metadata','music','sound','fonts','shaders'}
PROFILES={
    'timeline':{'folder':'tbcp_te_48a28e73_040dev','id':'af91bb93-0d4b-4d73-9a9f-d1898a39efda',
                'name':'TBCP 1 - Timeline Extended [48a28e73]'},
    'bpm':{'folder':'tbcp_bpm_d785d399_040dev','id':'63008eb1-d85e-4bdb-9670-0f2e1d1bd6af',
           'name':'TBCP 2 - Better Politics Mod [d785d399]'},
    'patch':{'folder':'tbcp_patch_040dev','id':'44a453ae-01a4-49e4-991c-4f1eaa2ae614',
             'name':'TBCP 3 - Compatibility '+VERSION},
}


def documents():
    """CSIDL_PERSONAL follows the user's redirected Documents Known Folder."""
    buffer=ctypes.create_unicode_buffer(32768)
    code=ctypes.windll.shell32.SHGetFolderPathW(None,5,None,0,buffer)
    if code:raise OSError('Cannot resolve Documents Known Folder: '+str(code))
    return Path(buffer.value)


def file_sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def profiles(lock,version):
    result={key:dict(value) for key,value in PROFILES.items()}
    for label,short,title in [('timeline','te','Timeline Extended'),('bpm','bpm','Better Politics Mod')]:
        commit=lock['mods'][label]['commit'];number=1 if label=='timeline' else 2
        result[label]['name']=f'TBCP {number} - {title} [{commit[:8]}]'
        original='48a28e73' if label=='timeline' else 'd785d399'
        if not commit.startswith(original) or version!='0.6.0-dev':
            result[label]['folder']=f'tbcp_{short}_{commit[:8]}_{version}'
            result[label]['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'tbcp/'+label+'/'+commit+'/'+version))
    result['patch']['name']='TBCP 3 - Compatibility '+version
    if version!='0.6.0-dev':result['patch']['folder']='tbcp_patch_'+version
    return result


def prepare(destination):
    lock=load_lock(ROOT)
    source_state(ROOT)
    selected=profiles(lock,VERSION)
    build=json.loads((ROOT/'docs/validation/build-manifest.json').read_text(encoding='utf-8'))
    assert build['version']==VERSION and not build['game_runs_performed']
    destination=destination.resolve()
    # Resolve and check all paths before creating the first package.
    targets={key:destination/config['folder'] for key,config in selected.items()}
    for target in targets.values():
        if target.exists():raise FileExistsError('Existing folder left untouched: '+str(target))
    plan={};input_manifest={}
    for label in ['timeline','bpm']:
        config=lock['mods'][label];checkout=Path(config['checkout']);mod=Path(config['mod_root'])
        commit=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
        assert commit==config['commit'],label
        tree=subprocess.check_output(['git','-C',str(checkout),'-c','core.quotepath=false','ls-tree','-r','HEAD'],text=True,encoding='utf-8')
        files=[]
        for line in tree.splitlines():
            info,rel=line.split('\t',1)
            source=checkout/rel
            try:runtime_relative=source.relative_to(mod)
            except ValueError:continue
            if runtime_relative.parts[0] not in RUNTIME_DIRECTORIES and runtime_relative.as_posix()!='thumbnail.png':continue
            # Verify the copied runtime tree against the pinned Git blobs,
            # accepting checkout-only CRLF conversion, never content changes.
            data=source.read_bytes();expected=info.split()[2]
            assert not data.startswith(b'version https://git-lfs.github.com/spec/v1'), 'Unmaterialized Git LFS asset: '+str(source)
            def blob(value):return hashlib.sha1(b'blob '+str(len(value)).encode()+b'\0'+value).hexdigest()
            assert expected in {blob(data),blob(data.replace(b'\r\n',b'\n'))},'Runtime input drift: '+str(source)
            files.append((source,runtime_relative))
        assert any(rel.as_posix()=='.metadata/metadata.json' for _,rel in files)
        plan[label]=files;input_manifest[label]={'commit':commit,'runtime_files':len(files)}
    plan['patch']=[(path,path.relative_to(OUTPUT)) for path in sorted(OUTPUT.rglob('*')) if path.is_file()]
    assert plan['patch']
    result={'version':VERSION,'source_commits':build['source_commits'],'destination':str(destination),
            'launch_performed':False,'playset_changed':False,'packages':{}}
    for label,files in plan.items():
        target=targets[label];target.mkdir(parents=True)
        for source,relative in files:
            output=target/relative;output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,output)
        metadata_path=target/'.metadata/metadata.json'
        metadata=json.loads(metadata_path.read_text(encoding='utf-8-sig'))
        original_identity={'name':metadata['name'],'id':metadata['id']}
        metadata['name']=selected[label]['name'];metadata['id']=selected[label]['id']
        # Dependency identity and ordering are set manually in a separate
        # launcher playset. Do not invent an unverified relationships schema.
        metadata['relationships']=[]
        metadata_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # Compare every copied file. The sole permitted change is local identity.
        for source,relative in files:
            if relative.as_posix()=='.metadata/metadata.json':continue
            assert file_sha(source)==file_sha(target/relative),'Copy mismatch: '+str(relative)
        result['packages'][label]={'path':str(target),'file_count':len(files),'name':metadata['name'],
                                  'local_id':metadata['id'],'original_identity':original_identity,
                                  'metadata_only_changes':['name','id','relationships']}
    result['source_runtime']=input_manifest
    report=ROOT/'docs/validation'/('installed-profile.json' if destination!=ROOT/'runtime/local-mods' else 'prepared-profile.json')
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--install',action='store_true')
    group.add_argument('--destination',type=Path)
    args=parser.parse_args()
    target=documents()/'Paradox Interactive/Victoria 3/mod' if args.install else (args.destination or ROOT/'runtime/local-mods')
    prepare(target)
