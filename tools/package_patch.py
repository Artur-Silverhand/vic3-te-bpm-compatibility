"""Deterministic local-development archive; no upload or game execution."""
import hashlib
import json
from pathlib import Path
import zipfile

from build_patch import ROOT, OUTPUT, VERSION, digest
from source_state import require_fresh_inputs,project


def package():
    build=json.loads((ROOT/'docs/validation/build-manifest.json').read_text(encoding='utf-8'))
    audit=json.loads((ROOT/'docs/validation/offline-audit.json').read_text(encoding='utf-8'))
    gate=json.loads((ROOT/'docs/validation/synthetic-gate.json').read_text(encoding='utf-8'))
    assert build['version']==VERSION
    assert not audit['unresolved_typed_references'] and not audit['unknown_replacements']
    assert not audit['duplicate_generated_entities']
    hashes={p.relative_to(OUTPUT).as_posix():digest(p) for p in sorted(OUTPUT.rglob('*')) if p.is_file()}
    assert hashes==audit['patch_sha256'],'Patch changed after audit; rerun tools/audit_patch.py'
    assert gate['status']=='PASS' and gate['version']==VERSION,'Synthetic gate failed or stale'
    assert gate['patch_sha256']==hashes,'Patch changed after synthetic gate; rerun tools/verify_patch.py'
    assert gate['tools_sha256']=={p.relative_to(ROOT).as_posix():digest(p) for p in sorted((ROOT/'tools').glob('*')) if p.suffix in {'.py','.ps1'}},'Tools changed after gate'
    require_fresh_inputs(gate,ROOT)
    metadata=json.loads((OUTPUT/'.metadata/metadata.json').read_text(encoding='utf-8'))
    assert metadata['version']==VERSION
    # No machine paths in distributable metadata/build identity.
    identity={'version':VERSION,'specification':'SPEC-002','game':project(ROOT)['supported_game_version'],
              'source_commits':build['source_commits'],'status':build['status'],
              'runtime_verified':False,'files_sha256':hashes,'open':build['open']}
    prefix='tbcp_compat_'+VERSION
    destination=ROOT/'dist'/('te-bpm-compatibility-'+VERSION+'.zip')
    destination.parent.mkdir(exist_ok=True)
    members={prefix+'/'+rel:(OUTPUT/rel).read_bytes() for rel in hashes}
    members[prefix+'/BUILD.json']=(json.dumps(identity,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    if destination.exists():
        with zipfile.ZipFile(destination) as previous:
            same=set(previous.namelist())==members.keys() and all(previous.read(name)==data for name,data in members.items())
        assert same,'Immutable release archive already exists; use a new patch version'
    if not destination.exists():
        with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for name,data in sorted(members.items()):
                entry=zipfile.ZipInfo(name,date_time=(2026,11,7,0,0,0))
                entry.compress_type=zipfile.ZIP_DEFLATED
                entry.create_system=3;entry.external_attr=0o100644<<16
                archive.writestr(entry,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist())==members.keys()
        for name,data in members.items():assert archive.read(name)==data,name
    result={'archive':destination.relative_to(ROOT).as_posix(),'version':VERSION,
            'sha256':digest(destination),'bytes':destination.stat().st_size,'members':len(members),
            'source_commits':build['source_commits'],'runtime_verified':False}
    (ROOT/'docs/validation/package.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':package()
