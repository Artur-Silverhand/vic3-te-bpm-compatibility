"""Prepare a separate upload copy; never rewrite the installed testing profile."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_patch import OUTPUT,VERSION,digest
from prepare_local_profile import documents

UPLOAD_ID='6a028d9f-19e5-4676-b3be-20c52d5ba63b'


def prepare(install=False):
    gate=json.loads((ROOT/'docs/validation/synthetic-gate.json').read_text(encoding='utf-8'))
    expected={p.relative_to(OUTPUT).as_posix():digest(p) for p in OUTPUT.rglob('*') if p.is_file()}
    assert gate['status']=='PASS' and gate['version']==VERSION
    assert gate['patch_sha256']==expected,'Patch changed since validation'
    assert gate['tools_sha256']=={p.relative_to(ROOT).as_posix():digest(p) for p in sorted((ROOT/'tools').glob('*')) if p.suffix in {'.py','.ps1'}}
    target=(ROOT/'release/workshop-content').resolve()
    assert target.parent==(ROOT/'release').resolve() and not target.exists()
    shutil.copytree(OUTPUT,target)
    path=target/'.metadata/metadata.json'
    metadata=json.loads(path.read_text(encoding='utf-8'))
    metadata.update({'id':UPLOAD_ID,'name':'Timeline Extended + BPM - Compatibility [Experimental]'})
    path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md',target/'THIRD_PARTY_NOTICES.md')
    (target/'CREDITS.md').write_text('''# Sources and credits

Independent experimental compatibility patch. Requires Timeline Extended and
full Better Politics Mod, installed separately. Not an official release of
either parent mod or Paradox. Original code retains its respective authorship.

- TE: https://github.com/jakeOmega/Vic3TimelineExtended — 48a28e73
- BPM: https://github.com/Better-Politics-Mod/Better-Politics-Mod-Vic-3 — d785d399
- Victoria 3 1.15.0: Paradox Interactive
- Patch: https://github.com/Artur-Silverhand/vic3-te-bpm-compatibility

See THIRD_PARTY_NOTICES.md. No new license for upstream code is granted here.
''',encoding='utf-8')
    identity={'version':VERSION,'synthetic_status':'PASS','tests':gate['tests_run'],
              'game':'1.15.0','gameplay_verified':False,
              'source_patch_sha256':expected,
              'delivery_only_changes':['.metadata/metadata.json','CREDITS.md','THIRD_PARTY_NOTICES.md','BUILD.json']}
    (target/'BUILD.json').write_text(json.dumps(identity,indent=2)+'\n',encoding='utf-8')
    for relative,sha in expected.items():
        if relative not in {'.metadata/metadata.json','CREDITS.md'}:assert digest(target/relative)==sha,relative
    result={'version':VERSION,'source':str(target),'upload_id':UPLOAD_ID,'game_launched':False,'playset_changed':False}
    if install:
        mod_root=(documents()/'Paradox Interactive/Victoria 3/mod').resolve()
        destination=(mod_root/'tbcp_workshop_060dev').resolve()
        assert destination.parent==mod_root and not destination.exists(),'Upload copy already exists'
        shutil.copytree(target,destination)
        result['installed_upload_copy']=str(destination)
    (ROOT/'release/workshop-upload-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--install',action='store_true')
    prepare(parser.parse_args().install)
